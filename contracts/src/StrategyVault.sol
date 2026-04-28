// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Initializable } from "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import {
    UUPSUpgradeable
} from "@openzeppelin/contracts-upgradeable/proxy/utils/UUPSUpgradeable.sol";
import {
    OwnableUpgradeable
} from "@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";
import {
    ReentrancyGuardTransient
} from "@openzeppelin/contracts/utils/ReentrancyGuardTransient.sol";
import { IERC20 } from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import { SafeERC20 } from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import { ECDSA } from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";

import { IStrategyVault } from "./interfaces/IStrategyVault.sol";
import { ITradeAttestationVerifier } from "./interfaces/ITradeAttestationVerifier.sol";

/// @title StrategyVault
/// @notice Per-strategy capital + ZK-gated trade execution + NAV tracking.
///         Phase 1 simplification: a single AllocatorVault is paired with each
///         StrategyVault at init (the demo wires Sentinel → 3 strategies).
///         Helios.md §6.4.
contract StrategyVault is
    IStrategyVault,
    Initializable,
    OwnableUpgradeable,
    ReentrancyGuardTransient,
    UUPSUpgradeable
{
    using SafeERC20 for IERC20;

    // Public-input layout decoded from publicInputs[]. MUST match the
    // declaration order in circuits/momentum_v1.circom's `public[...]`
    // and the _PUBLIC_INPUT_COUNT in MomentumV1VerifierAdapter.
    uint256 internal constant PI_TRADE_HASH = 0;
    uint256 internal constant PI_DECLARED_CLASS = 1;
    uint256 internal constant PI_STRATEGY_VAULT = 2;
    uint256 internal constant PI_PARAMS_HASH = 3;
    uint256 internal constant PI_ALLOCATOR = 4;
    uint256 internal constant PI_ASSET_IN = 5;
    uint256 internal constant PI_ASSET_OUT = 6;
    uint256 internal constant PI_AMOUNT_IN = 7;
    uint256 internal constant PI_MIN_AMOUNT_OUT = 8;
    uint256 internal constant PI_DIRECTION = 9;
    uint256 internal constant PI_NONCE = 10;
    uint256 internal constant PI_BLOCK_WINDOW_START = 11;
    uint256 internal constant PI_BLOCK_WINDOW_END = 12;
    uint256 internal constant PI_ORACLE_ROOT = 13;
    uint256 internal constant PI_LENGTH = 14;

    StrategyManifest internal _manifest;
    IERC20 public baseAsset;
    address public registry;
    address public verifier;
    address public allowedRouter;
    address public navOracle;
    address public allocatorVault;

    bool public halted;
    uint256 internal _totalNAV;
    uint64 public lastNAVTimestamp;

    mapping(address => uint256) internal _allocationOf;
    mapping(bytes32 => bool) internal _seenTradeHash;

    /// @dev Reserved storage for future upgrades. Append new state variables
    ///      ABOVE this gap and shrink it accordingly so storage layout stays compatible.
    uint256[50] private __gap;

    error ZeroAddress();
    error NotAllocatorVault();
    error NotNavOracle();
    error VaultHalted();
    error WrongTarget();
    error NonZeroValue();
    error WindowExpired();
    error WindowNotStarted();
    error TradeAlreadySettled();
    error PublicInputsTooShort();
    error AssetIndexOOB();
    error AmountInMismatch();
    error AllocationOverdrawn();
    error StaleNav();
    error NavSignatureInvalid();
    error TradeCallFailed(uint256 index);

    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }

    function initialize(
        StrategyManifest calldata manifest_,
        IERC20 baseAsset_,
        address registry_,
        address verifier_,
        address allowedRouter_,
        address navOracle_,
        address allocatorVault_,
        address owner_
    ) external initializer {
        if (
            manifest_.operator == address(0) || address(baseAsset_) == address(0)
                || registry_ == address(0) || verifier_ == address(0)
                || allowedRouter_ == address(0) || navOracle_ == address(0)
                || allocatorVault_ == address(0) || owner_ == address(0)
        ) revert ZeroAddress();

        __Ownable_init(owner_);

        _manifest = manifest_;
        baseAsset = baseAsset_;
        registry = registry_;
        verifier = verifier_;
        allowedRouter = allowedRouter_;
        navOracle = navOracle_;
        allocatorVault = allocatorVault_;
    }

    modifier onlyOperator() {
        if (msg.sender != _manifest.operator) revert NotOperator();
        _;
    }

    modifier onlyAllocatorVault() {
        if (msg.sender != allocatorVault) revert NotAllocatorVault();
        _;
    }

    modifier notHalted() {
        if (halted) revert VaultHalted();
        _;
    }

    function _authorizeUpgrade(address) internal override onlyOwner { }

    // ── Capital flow (allocator vault entry/exit) ───────────────────

    /// @notice Pull base-asset capital in from the paired allocator vault.
    function allocateFrom(uint256 amount) external onlyAllocatorVault notHalted nonReentrant {
        if (amount == 0) revert AmountInMismatch();
        baseAsset.safeTransferFrom(msg.sender, address(this), amount);
        _allocationOf[msg.sender] += amount;
        _totalNAV += amount;
        if (_totalNAV > _manifest.maxCapacity) revert CapacityExceeded();
    }

    function withdrawToAllocator(address allocator, uint256 amount)
        external
        onlyAllocatorVault
        nonReentrant
    {
        if (amount > _allocationOf[allocator]) revert AllocationOverdrawn();
        _allocationOf[allocator] -= amount;
        // NAV is tracked off-chain via signed reportNAV updates; the on-chain
        // base-asset balance is the hard truth. When the reported NAV signals
        // unrealized losses (NAV < principal), an unwind/defund still needs
        // to repatriate whatever underlying the strategy actually holds, so
        // we clamp _totalNAV to 0 rather than reverting. The asset transfer
        // below enforces the real constraint — if the strategy lacks the
        // base-asset balance, safeTransfer reverts.
        if (amount > _totalNAV) {
            emit NavClampedOnWithdraw(address(this), allocator, _totalNAV, amount);
            _totalNAV = 0;
        } else {
            _totalNAV -= amount;
        }
        baseAsset.safeTransfer(msg.sender, amount);
    }

    /// @notice Pay accrued realized PnL (NAV above principal) back to the allocator vault.
    function distributeRealized(address allocator) external onlyAllocatorVault nonReentrant {
        uint256 share = _navOf(allocator);
        uint256 principal = _allocationOf[allocator];
        if (share <= principal) {
            emit RealizedDistributed(address(this), allocator, 0);
            return;
        }
        uint256 realized = share - principal;
        _totalNAV -= realized;
        baseAsset.safeTransfer(msg.sender, realized);
        emit RealizedDistributed(address(this), allocator, realized);
    }

    // ── Trade execution (ZK-gated) ──────────────────────────────────

    function executeWithProof(
        bytes calldata proof,
        uint256[] calldata publicInputs,
        Call[] calldata trades
    ) external onlyOperator notHalted nonReentrant {
        _validateAndVerify(proof, publicInputs);
        _runTrades(trades);
        _emitTradeAttested(publicInputs);
    }

    function _validateAndVerify(bytes calldata proof, uint256[] calldata publicInputs) internal {
        if (publicInputs.length < PI_LENGTH) revert PublicInputsTooShort();

        // Bind the proof to this specific (class, vault, allocator, params) tuple.
        // Without these checks a proof generated for a different vault, allocator,
        // or operator-parameter set could be replayed here.
        if (bytes32(publicInputs[PI_DECLARED_CLASS]) != _manifest.declaredClass) {
            revert ClassMismatch();
        }
        if (address(uint160(publicInputs[PI_STRATEGY_VAULT])) != address(this)) {
            revert VaultMismatch();
        }
        if (bytes32(publicInputs[PI_PARAMS_HASH]) != _manifest.paramsHash) {
            revert ParamsHashMismatch();
        }
        if (address(uint160(publicInputs[PI_ALLOCATOR])) != allocatorVault) {
            revert AllocatorMismatch();
        }

        uint256 universeLen = _manifest.assetUniverse.length;
        if (publicInputs[PI_ASSET_IN] >= universeLen || publicInputs[PI_ASSET_OUT] >= universeLen) {
            revert AssetIndexOOB();
        }
        if (block.number < publicInputs[PI_BLOCK_WINDOW_START]) revert WindowNotStarted();
        if (block.number > publicInputs[PI_BLOCK_WINDOW_END]) revert WindowExpired();

        bytes32 tradeHash = bytes32(publicInputs[PI_TRADE_HASH]);
        if (_seenTradeHash[tradeHash]) revert TradeAlreadySettled();
        _seenTradeHash[tradeHash] = true;

        if (!ITradeAttestationVerifier(verifier)
                .verify(_manifest.declaredClass, proof, publicInputs)) revert InvalidProof();
    }

    function _runTrades(Call[] calldata trades) internal {
        for (uint256 i = 0; i < trades.length; i++) {
            Call calldata c = trades[i];
            if (c.value != 0) revert NonZeroValue();
            if (c.target != allowedRouter && !_isUniverseAsset(c.target)) revert WrongTarget();
            (bool success,) = c.target.call(c.data);
            if (!success) revert TradeCallFailed(i);
        }
    }

    function _emitTradeAttested(uint256[] calldata publicInputs) internal {
        emit TradeAttested(
            address(this),
            allocatorVault,
            bytes32(publicInputs[PI_TRADE_HASH]),
            _manifest.declaredClass,
            _manifest.assetUniverse[publicInputs[PI_ASSET_IN]],
            _manifest.assetUniverse[publicInputs[PI_ASSET_OUT]],
            publicInputs[PI_AMOUNT_IN],
            publicInputs[PI_MIN_AMOUNT_OUT],
            uint8(publicInputs[PI_DIRECTION]),
            uint64(publicInputs[PI_BLOCK_WINDOW_START]),
            uint64(publicInputs[PI_BLOCK_WINDOW_END])
        );
    }

    // ── NAV reporting (off-chain signed) ────────────────────────────

    /// @notice Apply an off-chain NAV snapshot signed by `navOracle`.
    /// @dev signedNAV = abi.encode(uint256 totalNAV, uint64 timestamp, bytes signature).
    ///      The signature is over
    ///      keccak256(abi.encode(block.chainid, address(this), totalNAV, timestamp))
    ///      with no EIP-191 prefix — the oracle signs the raw digest directly.
    ///      block.chainid binds the signature to a specific chain so the same
    ///      NAV update cannot be replayed against a sibling vault on another chain.
    function reportNAV(bytes calldata signedNAV) external {
        (uint256 totalNAV_, uint64 timestamp, bytes memory signature) =
            abi.decode(signedNAV, (uint256, uint64, bytes));
        if (timestamp <= lastNAVTimestamp) revert StaleNav();
        bytes32 digest = keccak256(abi.encode(block.chainid, address(this), totalNAV_, timestamp));
        address signer = ECDSA.recover(digest, signature);
        if (signer != navOracle) revert NavSignatureInvalid();

        _totalNAV = totalNAV_;
        lastNAVTimestamp = timestamp;
        emit NAVReported(address(this), totalNAV_, timestamp);
    }

    // ── Slash (registry-only halt) ──────────────────────────────────

    function slash(string calldata reason) external {
        if (msg.sender != registry) revert NotRegistry();
        halted = true;
        emit Slashed(address(this), 0, reason);
    }

    // ── Views ───────────────────────────────────────────────────────

    function manifest() external view returns (StrategyManifest memory) {
        return _manifest;
    }

    function totalNAV() external view returns (uint256) {
        return _totalNAV;
    }

    function navOf(address allocator) external view returns (uint256) {
        return _navOf(allocator);
    }

    function allocationOf(address allocator) external view returns (uint256) {
        return _allocationOf[allocator];
    }

    function isTradeHashSeen(bytes32 tradeHash) external view returns (bool) {
        return _seenTradeHash[tradeHash];
    }

    // ── Internal helpers ────────────────────────────────────────────

    function _navOf(address allocator) internal view returns (uint256) {
        // Phase 1: single allocator vault, so totalAllocated == _allocationOf[allocatorVault].
        uint256 totalAlloc = _allocationOf[allocatorVault];
        if (totalAlloc == 0) return 0;
        return (_totalNAV * _allocationOf[allocator]) / totalAlloc;
    }

    function _isUniverseAsset(address target) internal view returns (bool) {
        address[] storage u = _manifest.assetUniverse;
        for (uint256 i = 0; i < u.length; i++) {
            if (u[i] == target) return true;
        }
        return false;
    }
}
