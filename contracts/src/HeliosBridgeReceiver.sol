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

        (uint8 action, bytes32 strategyId, address remoteVault, address user) =
            abi.decode(inner, (uint8, bytes32, address, address));

        if (action == ACTION_ALLOCATE) {
            _allocate(srcEid, strategyId, remoteVault, user, amountLD);
        } else if (action == ACTION_SETTLE_DEFUND) {
            _settleDefund(srcEid, strategyId, user, amountLD);
        } else {
            revert UnknownAction(action);
        }
    }

    function _allocate(
        uint32 srcEid,
        bytes32, /*strategyId*/
        address remoteVault,
        address user,
        uint256 amount
    ) internal {
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
