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
import { IStrategyRegistry } from "./interfaces/IStrategyRegistry.sol";
import { IOracleAnchor } from "./interfaces/IOracleAnchor.sol";

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

    // Yield-rotation public-input layout. Distinct from the swap layout
    // above — rotations move capital between yield-bearing markets and
    // bind a different witness set. MUST match circuits/yield_rotation_v1.circom.
    uint256 internal constant PI_YR_TRADE_HASH = 0;
    uint256 internal constant PI_YR_DECLARED_CLASS = 1;
    uint256 internal constant PI_YR_M_FROM = 2;
    uint256 internal constant PI_YR_M_TO = 3;
    uint256 internal constant PI_YR_AMOUNT = 4;
    uint256 internal constant PI_YR_YIELD_ORACLE_ROOT = 5;
    uint256 internal constant PI_YR_ALLOCATOR = 6;
    uint256 internal constant PI_YR_NONCE = 7;
    uint256 internal constant PI_YR_BLOCK_WINDOW_END = 8;
    uint256 internal constant PI_YR_LENGTH = 9;

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

    /// @notice Anchors that authenticate `oracle_root` / `yield_oracle_root`
    ///         public inputs. Without these the prover can mint a Poseidon
    ///         root over fictitious prices and pass the verifier — Helios.md
    ///         §9.3 requires the trade's oracle root be one the off-chain
    ///         oracle has actually attested.
    address public priceAnchor;
    address public yieldAnchor;

    /// @dev Reserved storage for future upgrades. Append new state variables
    ///      ABOVE this gap and shrink it accordingly so storage layout stays compatible.
    uint256[48] private __gap;

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
    error UnknownOracleRoot();
    error UnknownYieldOracleRoot();

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
        address priceAnchor_,
        address yieldAnchor_,
        address owner_
    ) external initializer {
        if (
            manifest_.operator == address(0) || address(baseAsset_) == address(0)
                || registry_ == address(0) || verifier_ == address(0)
                || allowedRouter_ == address(0) || navOracle_ == address(0)
                || allocatorVault_ == address(0) || priceAnchor_ == address(0)
                || yieldAnchor_ == address(0) || owner_ == address(0)
        ) revert ZeroAddress();

        __Ownable_init(owner_);

        _manifest = manifest_;
        baseAsset = baseAsset_;
        registry = registry_;
        verifier = verifier_;
        allowedRouter = allowedRouter_;
        navOracle = navOracle_;
        allocatorVault = allocatorVault_;
        priceAnchor = priceAnchor_;
        yieldAnchor = yieldAnchor_;
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

    /// @notice yield_rotation_v1 entry path. The 9-PI layout omits asset
    ///         indices, params_hash, and an explicit window-start (rotation
    ///         is whole-position; the allocator picks the destination
    ///         market). Private witnesses bound by the circuit but not
    ///         visible here:
    ///           - signal_threshold (operator-declared APY-diff gate)
    ///           - bridging_cost
    ///           - markets_allowlist_root (canonical root lives in
    ///             StrategyRegistry.marketAllowlistRoot — operators are
    ///             expected to use it; full on-chain enforcement requires
    ///             promoting that root to a public input in the circuit,
    ///             which is a v2 change).
    /// @dev TODO(WS7.A): once Poseidon-on-Solidity ships, recompute the
    ///      YR trade_hash here against the registry's committed paramsHash
    ///      to defend against operators feeding stale params into a fresh
    ///      proof. The circuit already enforces the binding between
    ///      private witnesses and the trade_hash.
    function executeYieldRotationWithProof(
        bytes calldata proof,
        uint256[] calldata publicInputs,
        Call[] calldata trades
    ) external onlyOperator notHalted nonReentrant {
        _validateAndVerifyYR(proof, publicInputs);
        _runTrades(trades);
        _emitYieldRotationAttested(publicInputs);
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
        if (bytes32(publicInputs[PI_PARAMS_HASH]) != _activeParamsHash()) {
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

        // Bind the proof's `oracle_root` to a root the off-chain oracle has
        // actually committed via OraclePriceAnchor. Without this an operator
        // can fabricate price observations, hash them into a Poseidon root,
        // and pass the verifier — the proof is valid for *some* market state
        // but not for one the protocol has signed off on.
        if (!IOracleAnchor(priceAnchor).isKnownRoot(bytes32(publicInputs[PI_ORACLE_ROOT]))) {
            revert UnknownOracleRoot();
        }

        bytes32 tradeHash = bytes32(publicInputs[PI_TRADE_HASH]);
        if (_seenTradeHash[tradeHash]) revert TradeAlreadySettled();
        _seenTradeHash[tradeHash] = true;

        if (!ITradeAttestationVerifier(verifier)
                .verify(_manifest.declaredClass, proof, publicInputs)) revert InvalidProof();
    }

    function _validateAndVerifyYR(bytes calldata proof, uint256[] calldata publicInputs) internal {
        if (publicInputs.length < PI_YR_LENGTH) revert PublicInputsTooShort();

        if (bytes32(publicInputs[PI_YR_DECLARED_CLASS]) != _manifest.declaredClass) {
            revert ClassMismatch();
        }
        if (address(uint160(publicInputs[PI_YR_ALLOCATOR])) != allocatorVault) {
            revert AllocatorMismatch();
        }
        if (block.number > publicInputs[PI_YR_BLOCK_WINDOW_END]) revert WindowExpired();

        // Same binding as above, against the yield-anchor's domain. The
        // anchors enforce signature-domain separation (different EIP-712
        // type-hashes) so a price-domain commit cannot be replayed here.
        if (!IOracleAnchor(yieldAnchor).isKnownRoot(bytes32(publicInputs[PI_YR_YIELD_ORACLE_ROOT])))
        {
            revert UnknownYieldOracleRoot();
        }

        bytes32 tradeHash = bytes32(publicInputs[PI_YR_TRADE_HASH]);
        if (_seenTradeHash[tradeHash]) revert TradeAlreadySettled();
        _seenTradeHash[tradeHash] = true;

        if (!ITradeAttestationVerifier(verifier)
                .verify(_manifest.declaredClass, proof, publicInputs)) revert InvalidProof();
    }

    function _emitYieldRotationAttested(uint256[] calldata publicInputs) internal {
        emit YieldRotationAttested(
            address(this),
            allocatorVault,
            bytes32(publicInputs[PI_YR_TRADE_HASH]),
            _manifest.declaredClass,
            publicInputs[PI_YR_M_FROM],
            publicInputs[PI_YR_M_TO],
            publicInputs[PI_YR_AMOUNT],
            bytes32(publicInputs[PI_YR_YIELD_ORACLE_ROOT]),
            uint64(publicInputs[PI_YR_BLOCK_WINDOW_END])
        );
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

    /// @notice The currently-binding params hash. WS7.A: prefer the
    ///         registry-committed value when present so post-rotation
    ///         proofs validate against the canonical hash; fall back to
    ///         the manifest value for vaults that haven't yet committed
    ///         (Phase-1 deployment path).
    function _activeParamsHash() internal view returns (bytes32) {
        bytes32 fromRegistry = IStrategyRegistry(registry).paramsHashOf(address(this));
        if (fromRegistry != bytes32(0)) return fromRegistry;
        return _manifest.paramsHash;
    }

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
