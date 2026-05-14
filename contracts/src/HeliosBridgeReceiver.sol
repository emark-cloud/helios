// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {
    ILayerZeroComposer
} from "@layerzerolabs/lz-evm-protocol-v2/contracts/interfaces/ILayerZeroComposer.sol";
import { OFTComposeMsgCodec } from "@layerzerolabs/oapp-evm/oft/libs/OFTComposeMsgCodec.sol";
import { IERC20 } from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import { SafeERC20 } from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import { Ownable } from "@openzeppelin/contracts/access/Ownable.sol";

interface IStrategyVaultCrossChain {
    function onCrossChainAllocate(uint256 amount, address user) external;
}

interface IAllocatorVaultCrossChain {
    function settleRemoteDefund(address user, bytes32 strategyId, uint256 amount, uint32 srcEid)
        external;
}

/// @title HeliosBridgeReceiver
/// @notice CXR-0b — `lzCompose` handler on each chain. Receives the
///         credited mUSDC from `MUsdcOFTAdapter._credit` and atomically
///         dispatches it to either a local StrategyVault (allocate
///         path) or the local AllocatorVault (defund settlement path).
///
///         Trust model:
///           - msg.sender must be the local LZ V2 endpoint (which
///             invokes lzCompose after OFT credit succeeds).
///           - The `_from` argument must equal the local trusted OFT
///             adapter; this is the address that called `endpoint.sendCompose`.
///           - The OFT compose payload's `composeFrom` field encodes the
///             remote OApp/adapter that authored the message; ignored
///             here but emitted in the event for off-chain audit.
///
///         On revert (e.g. capacity exceeded, strategy paused) the
///         credited mUSDC is parked in `recoverable[user]` so a manual
///         `recover()` returns it to the user. Without this fallback,
///         a single bad allocate would strand funds in the receiver.
contract HeliosBridgeReceiver is ILayerZeroComposer, Ownable {
    using SafeERC20 for IERC20;

    /// @notice OFT credit action discriminator.
    uint8 internal constant ACTION_ALLOCATE = 0;
    uint8 internal constant ACTION_SETTLE_DEFUND = 1;
    /// @notice CXR-cost Tier 2 — batched ALLOCATE shape. ComposeMsg
    ///         encodes arrays of (strategyId, amount, remoteVault) +
    ///         user; this receiver loops `_allocateOne` per index.
    ///         Mirror of `AllocatorVault.CXR_ACTION_ALLOCATE_BATCH`.
    uint8 internal constant ACTION_ALLOCATE_BATCH = 2;
    /// @notice Bound on entries per batched compose. Matches
    ///         `AllocatorVault.CXR_MAX_BATCH_SIZE`. lzCompose runs at
    ///         200k gas budget; 16 entries leave comfortable headroom.
    uint256 internal constant MAX_BATCH_SIZE = 16;

    IERC20 public immutable usdc;
    address public immutable endpoint;
    address public immutable oftAdapter;

    /// @dev Local AllocatorVault — used on Kite to settle defunds. May
    ///      be zero on execution chains where defunds originate but
    ///      never land.
    address public allocatorVault;

    /// @notice user → parked balance after a failed compose. Owner
    ///         settles via `recover` once the cause is resolved.
    mapping(address user => uint256 amount) public recoverable;

    event CrossChainAllocateExecuted(
        uint32 indexed srcEid, address indexed strategy, address indexed user, uint256 amount
    );
    event CrossChainDefundSettled(
        uint32 indexed srcEid, bytes32 indexed strategyId, address indexed user, uint256 amount
    );
    event AllocateFailed(
        uint32 indexed srcEid,
        address indexed strategy,
        address indexed user,
        uint256 amount,
        bytes reason
    );
    event Recovered(address indexed user, uint256 amount);

    error NotEndpoint();
    error UntrustedComposeFrom();
    error UnknownAction(uint8 action);
    error AllocatorVaultUnset();
    error MalformedComposeMsg();
    error InvalidBatchSize(uint256 size);
    error MismatchedBatchArrays();
    error BatchAmountMismatch(uint256 sum, uint256 expected);

    constructor(address usdc_, address endpoint_, address oftAdapter_, address owner_)
        Ownable(owner_)
    {
        require(
            usdc_ != address(0) && endpoint_ != address(0) && oftAdapter_ != address(0), "zero addr"
        );
        usdc = IERC20(usdc_);
        endpoint = endpoint_;
        oftAdapter = oftAdapter_;
    }

    /// @notice Allow the owner to set the local AllocatorVault address.
    ///         Only meaningful on Kite (the canonical accounting chain).
    function setAllocatorVault(address av) external onlyOwner {
        allocatorVault = av;
    }

    /// @inheritdoc ILayerZeroComposer
    function lzCompose(
        address _from,
        bytes32, /*_guid*/
        bytes calldata _message,
        address, /*_executor*/
        bytes calldata /*_extraData*/
    )
        external
        payable
        override
    {
        if (msg.sender != endpoint) revert NotEndpoint();
        if (_from != oftAdapter) revert UntrustedComposeFrom();

        uint256 amountLD = OFTComposeMsgCodec.amountLD(_message);
        uint32 srcEid = OFTComposeMsgCodec.srcEid(_message);
        bytes memory inner = OFTComposeMsgCodec.composeMsg(_message);

        // Peek the action discriminator without committing to a decode
        // shape — the single-call (action 0/1) and batched (action 2)
        // payloads have different ABI tuple types so we must branch
        // before the full abi.decode.
        uint8 action = _peekAction(inner);

        if (action == ACTION_ALLOCATE) {
            (, /*action*/ bytes32 strategyId, address remoteVault, address user) =
                abi.decode(inner, (uint8, bytes32, address, address));
            // strategyId is unused on the receiver side — emitted by
            // the sender's RemoteAllocationSent; the receiver's event
            // is keyed on the remote vault address.
            strategyId; // silence unused-var warning
            _allocateOne(srcEid, remoteVault, user, amountLD);
        } else if (action == ACTION_SETTLE_DEFUND) {
            (, bytes32 strategyId, /*remoteVault*/, address user) =
                abi.decode(inner, (uint8, bytes32, address, address));
            _settleDefund(srcEid, strategyId, user, amountLD);
        } else if (action == ACTION_ALLOCATE_BATCH) {
            (
                ,
                /*action*/
                bytes32[] memory strategyIds,
                uint256[] memory amounts,
                address[] memory remoteVaults,
                address user
            ) = abi.decode(inner, (uint8, bytes32[], uint256[], address[], address));
            strategyIds; // strategyIds unused on receiver; sender event covers it
            _allocateBatch(srcEid, amounts, remoteVaults, user, amountLD);
        } else {
            revert UnknownAction(action);
        }
    }

    /// @dev Peek the first uint8 in an ABI-encoded payload without
    ///      committing to a full decode. Action discriminator occupies
    ///      the low byte of the first 32-byte head slot.
    function _peekAction(bytes memory inner) internal pure returns (uint8) {
        if (inner.length < 32) revert MalformedComposeMsg();
        uint256 slot;
        assembly {
            slot := mload(add(inner, 32))
        }
        return uint8(slot);
    }

    /// @dev Single-entry allocate dispatch. Shared between the
    ///      single-call (ACTION_ALLOCATE) and batched (ACTION_ALLOCATE_BATCH)
    ///      paths. On revert, the per-entry amount is parked in
    ///      `recoverable[user]` so a sibling entry in the same batch
    ///      can still settle.
    function _allocateOne(uint32 srcEid, address remoteVault, address user, uint256 amount)
        internal
    {
        usdc.safeTransfer(remoteVault, amount);
        try IStrategyVaultCrossChain(remoteVault).onCrossChainAllocate(amount, user) {
            emit CrossChainAllocateExecuted(srcEid, remoteVault, user, amount);
        } catch (bytes memory reason) {
            // Strategy refused (e.g. paused, capacity). Park funds.
            // Note: USDC has already moved to the vault; user can call
            // recover() after the operator forwards from the vault.
            recoverable[user] += amount;
            emit AllocateFailed(srcEid, remoteVault, user, amount, reason);
        }
    }

    /// @dev Batched allocate dispatch. Each entry calls `_allocateOne`
    ///      so a per-entry revert doesn't roll back the rest of the
    ///      batch — failing entries fall through to `recoverable[user]`
    ///      while siblings still settle into their target vaults.
    ///      Sum-of-amounts MUST equal the OFT-credited `totalAmountLD`
    ///      to avoid stranding capital in this receiver.
    function _allocateBatch(
        uint32 srcEid,
        uint256[] memory amounts,
        address[] memory remoteVaults,
        address user,
        uint256 totalAmountLD
    ) internal {
        uint256 n = amounts.length;
        if (n == 0 || n > MAX_BATCH_SIZE) revert InvalidBatchSize(n);
        if (remoteVaults.length != n) revert MismatchedBatchArrays();
        uint256 sum;
        for (uint256 i; i < n; ++i) {
            sum += amounts[i];
        }
        if (sum != totalAmountLD) revert BatchAmountMismatch(sum, totalAmountLD);
        for (uint256 i; i < n; ++i) {
            _allocateOne(srcEid, remoteVaults[i], user, amounts[i]);
        }
    }

    function _settleDefund(uint32 srcEid, bytes32 strategyId, address user, uint256 amount)
        internal
    {
        if (allocatorVault == address(0)) revert AllocatorVaultUnset();
        usdc.safeTransfer(allocatorVault, amount);
        IAllocatorVaultCrossChain(allocatorVault)
            .settleRemoteDefund(user, strategyId, amount, srcEid);
        emit CrossChainDefundSettled(srcEid, strategyId, user, amount);
    }

    /// @notice Owner-triggered recovery for parked funds. Forwards to user.
    function recover(address user) external onlyOwner {
        uint256 amt = recoverable[user];
        require(amt != 0, "nothing to recover");
        recoverable[user] = 0;
        usdc.safeTransfer(user, amt);
        emit Recovered(user, amt);
    }
}
