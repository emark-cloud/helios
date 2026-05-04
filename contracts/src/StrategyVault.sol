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
    EIP712Upgradeable
} from "@openzeppelin/contracts-upgradeable/utils/cryptography/EIP712Upgradeable.sol";
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
    EIP712Upgradeable,
    ReentrancyGuardTransient,
    UUPSUpgradeable
{
    using SafeERC20 for IERC20;

    /// @dev EIP-712 typehash for off-chain NAV updates. Bound to
    ///      `(name="HeliosStrategyVault", version="1", chainId, verifyingContract)`
    ///      by `_hashTypedDataV4`, so a navOracle signature for vault A on
    ///      chain X cannot be replayed against vault B or onto another chain.
    bytes32 internal constant _NAV_UPDATE_TYPEHASH =
        keccak256("NAVUpdate(uint256 totalNAV,uint64 timestamp)");

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
    uint256 internal constant PI_YR_STRATEGY_VAULT = 2;
    uint256 internal constant PI_YR_PARAMS_HASH = 3;
    uint256 internal constant PI_YR_ALLOWLIST_ROOT = 4;
    uint256 internal constant PI_YR_M_FROM = 5;
    uint256 internal constant PI_YR_M_TO = 6;
    uint256 internal constant PI_YR_AMOUNT = 7;
    uint256 internal constant PI_YR_YIELD_ORACLE_ROOT = 8;
    uint256 internal constant PI_YR_ALLOCATOR = 9;
    uint256 internal constant PI_YR_NONCE = 10;
    uint256 internal constant PI_YR_BLOCK_WINDOW_END = 11;
    uint256 internal constant PI_YR_LENGTH = 12;

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
    error AllowlistRootMismatch();

    /// @dev Selector for `IERC20.approve(address,uint256)`. Hardcoded so the
    ///      whitelist is independent of compile-time IERC20 metadata changes.
    bytes4 internal constant _APPROVE_SELECTOR = IERC20.approve.selector;

    /// @dev Selector for the canonical Algebra-Integral exactInputSingle
    ///      shape: `(address tokenIn, address tokenOut, address recipient,
    ///      uint256 deadline, uint256 amountIn, uint256 amountOutMinimum,
    ///      uint160 limitSqrtPrice)`. Phase-1's MockSwapRouter mirrors this
    ///      tuple exactly so the binding here applies to both the mock and
    ///      the real router on Kite mainnet (only the deployed address
    ///      changes — see MockSwapRouter NatSpec).
    bytes4 internal constant _EXACT_INPUT_SINGLE_SELECTOR = bytes4(
        keccak256("exactInputSingle((address,address,address,uint256,uint256,uint256,uint160))")
    );

    /// @notice Bundled initializer params. Bundled because passing 10 distinct
    ///         arguments blows the no-optimizer build's 16-stack-slot ceiling
    ///         under `forge coverage` (Stack too deep).
    struct InitParams {
        StrategyManifest manifest;
        IERC20 baseAsset;
        address registry;
        address verifier;
        address allowedRouter;
        address navOracle;
        address allocatorVault;
        address priceAnchor;
        address yieldAnchor;
        address owner;
    }

    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }

    function initialize(InitParams calldata p) external initializer {
        if (
            p.manifest.operator == address(0) || address(p.baseAsset) == address(0)
                || p.registry == address(0) || p.verifier == address(0)
                || p.allowedRouter == address(0) || p.navOracle == address(0)
                || p.allocatorVault == address(0) || p.priceAnchor == address(0)
                || p.yieldAnchor == address(0) || p.owner == address(0)
        ) revert ZeroAddress();

        __Ownable_init(p.owner);
        __EIP712_init("HeliosStrategyVault", "1");

        _manifest = p.manifest;
        baseAsset = p.baseAsset;
        registry = p.registry;
        verifier = p.verifier;
        allowedRouter = p.allowedRouter;
        navOracle = p.navOracle;
        allocatorVault = p.allocatorVault;
        priceAnchor = p.priceAnchor;
        yieldAnchor = p.yieldAnchor;
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
        _runSwapTrades(publicInputs, trades);
        _emitTradeAttested(publicInputs);
    }

    /// @notice yield_rotation_v1 entry path. The 12-PI layout omits asset
    ///         indices and an explicit window-start (rotation is
    ///         whole-position; the allocator picks the destination
    ///         market) but binds the same hardening fields as the swap
    ///         path: vault address, params hash, and the registry's
    ///         markets allowlist root. Private witnesses bound by the
    ///         circuit but not visible on chain:
    ///           - signal_threshold (operator-declared APY-diff gate;
    ///             commitment lives in publicInputs[PI_YR_PARAMS_HASH]
    ///             and is checked against `_activeParamsHash()`)
    ///           - bridging_cost (same)
    ///           - APY snapshots and Merkle paths under the yield-oracle
    ///             and allowlist roots
    function executeYieldRotationWithProof(
        bytes calldata proof,
        uint256[] calldata publicInputs,
        Call[] calldata trades
    ) external onlyOperator notHalted nonReentrant {
        _validateAndVerifyYR(proof, publicInputs);
        // YR rotation execution is a cross-chain bridge call — the binding
        // circuit for that calldata is Phase-5 work. Until then, the proof's
        // (m_from, m_to, amount) commitment is the rotation receipt and
        // any non-empty trades[] would bypass it. phase2-review.md item 4.
        if (trades.length != 0) revert YRTradesNotSupported();
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
        // Cross-vault replay guard. Without this, two YR vaults registered
        // under one allocator could replay each other's freshly-attested
        // proofs — phase2-review.md C-2.
        if (address(uint160(publicInputs[PI_YR_STRATEGY_VAULT])) != address(this)) {
            revert VaultMismatch();
        }
        // Bind the proof to the registry-committed (signal_threshold,
        // bridging_cost) tuple via Poseidon(t, b). Without this, the
        // operator could lower the threshold per-trade and pass any
        // signal — phase2-review.md C-3.
        if (bytes32(publicInputs[PI_YR_PARAMS_HASH]) != _activeParamsHash()) {
            revert ParamsHashMismatch();
        }
        // Bind to the registry-committed allowlist root for this class.
        // Without this, `setMarketAllowlistRoot` is decoration —
        // phase2-review.md C-3.
        if (
            bytes32(publicInputs[PI_YR_ALLOWLIST_ROOT])
                != IStrategyRegistry(registry).marketAllowlistRoot(_manifest.declaredClass)
        ) {
            revert AllowlistRootMismatch();
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

    /// @dev Execute the swap-path trade calls. Each call is bound to the
    ///      proof: the only accepted shapes are
    ///        - `IERC20.approve(allowedRouter, publicInputs[PI_AMOUNT_IN])`
    ///          on a universe-asset target, and
    ///        - `exactInputSingle(...)` on `allowedRouter`, with each
    ///          decoded field equal to its proof-committed counterpart.
    ///      Without this binding the operator could ship arbitrary calldata
    ///      (`assetIn.transfer(operator, balance)`) and the proof would
    ///      attest only intent. phase2-review.md item 4.
    function _runSwapTrades(uint256[] calldata publicInputs, Call[] calldata trades) internal {
        address routerAddr = allowedRouter;
        address assetIn = _manifest.assetUniverse[publicInputs[PI_ASSET_IN]];
        address assetOut = _manifest.assetUniverse[publicInputs[PI_ASSET_OUT]];
        uint256 amountIn = publicInputs[PI_AMOUNT_IN];
        uint256 minAmountOut = publicInputs[PI_MIN_AMOUNT_OUT];

        for (uint256 i = 0; i < trades.length; i++) {
            Call calldata c = trades[i];
            if (c.value != 0) revert NonZeroValue();
            bool targetIsRouter = c.target == routerAddr;
            bool targetIsAsset = !targetIsRouter && _isUniverseAsset(c.target);
            if (!targetIsRouter && !targetIsAsset) revert WrongTarget();

            if (c.data.length < 4) revert TradeCallSelectorNotAllowed();
            bytes4 selector = bytes4(c.data[:4]);

            if (targetIsAsset) {
                if (selector != _APPROVE_SELECTOR) revert TradeCallSelectorNotAllowed();
                _validateApproveCall(c.data, routerAddr, amountIn);
            } else {
                if (selector != _EXACT_INPUT_SINGLE_SELECTOR) {
                    revert TradeCallSelectorNotAllowed();
                }
                _validateExactInputSingleCall(c.data, assetIn, assetOut, amountIn, minAmountOut);
            }

            (bool success,) = c.target.call(c.data);
            if (!success) revert TradeCallFailed(i);
        }
    }

    function _validateApproveCall(
        bytes calldata data,
        address expectedSpender,
        uint256 expectedAmount
    ) internal pure {
        (address spender, uint256 amount) = abi.decode(data[4:], (address, uint256));
        if (spender != expectedSpender) revert ApproveSpenderMismatch();
        if (amount != expectedAmount) revert ApproveAmountMismatch();
    }

    /// @dev Decode `exactInputSingle((address,address,address,uint256,uint256,uint256,uint160))`
    ///      and bind every proof-relevant field. `deadline` and
    ///      `limitSqrtPrice` are operational — the operator picks them, so
    ///      they're outside the proof and outside the binding.
    function _validateExactInputSingleCall(
        bytes calldata data,
        address expectedTokenIn,
        address expectedTokenOut,
        uint256 expectedAmountIn,
        uint256 expectedMinOut
    ) internal view {
        (
            address tokenIn,
            address tokenOut,
            address recipient,,
            uint256 amountIn,
            uint256 amountOutMinimum,
        ) = abi.decode(data[4:], (address, address, address, uint256, uint256, uint256, uint160));
        if (tokenIn != expectedTokenIn) revert SwapTokenInMismatch();
        if (tokenOut != expectedTokenOut) revert SwapTokenOutMismatch();
        if (recipient != address(this)) revert SwapRecipientMismatch();
        if (amountIn != expectedAmountIn) revert SwapAmountInMismatch();
        if (amountOutMinimum != expectedMinOut) revert SwapMinOutMismatch();
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
    ///      The signature is EIP-712 typed-data over
    ///      `NAVUpdate(uint256 totalNAV, uint64 timestamp)` under the domain
    ///      `(HeliosStrategyVault, "1", chainId, verifyingContract)`. The
    ///      domain pins the digest to (a) this chain and (b) this vault, so
    ///      a navOracle signature cannot be replayed against a sibling vault
    ///      or onto a different chain. The pre-Phase-2 raw-digest format is
    ///      unsupported — signers must produce typed-data signatures.
    function reportNAV(bytes calldata signedNAV) external {
        (uint256 totalNAV_, uint64 timestamp, bytes memory signature) =
            abi.decode(signedNAV, (uint256, uint64, bytes));
        if (timestamp <= lastNAVTimestamp) revert StaleNav();
        bytes32 structHash = keccak256(abi.encode(_NAV_UPDATE_TYPEHASH, totalNAV_, timestamp));
        bytes32 digest = _hashTypedDataV4(structHash);
        address signer = ECDSA.recover(digest, signature);
        if (signer != navOracle) revert NavSignatureInvalid();

        _totalNAV = totalNAV_;
        lastNAVTimestamp = timestamp;
        emit NAVReported(address(this), totalNAV_, timestamp);
    }

    /// @notice Helper for off-chain signers — exposes the EIP-712 digest the
    ///         vault expects for a given NAV/timestamp tuple. Mirrors the
    ///         `_hashTypedDataV4(structHash)` path inside `reportNAV` so a
    ///         signer can debug a recovered-address mismatch against a
    ///         deterministic source of truth.
    function navDigest(uint256 totalNAV_, uint64 timestamp) external view returns (bytes32) {
        bytes32 structHash = keccak256(abi.encode(_NAV_UPDATE_TYPEHASH, totalNAV_, timestamp));
        return _hashTypedDataV4(structHash);
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
