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
    PausableUpgradeable
} from "@openzeppelin/contracts-upgradeable/utils/PausableUpgradeable.sol";
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
    PausableUpgradeable,
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
    uint256 internal constant PI_YR_BLOCK_WINDOW_START = 12;
    uint256 internal constant PI_YR_LENGTH = 13;

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

    /// @dev Storage slots that USED to hold `priceAnchor` / `yieldAnchor`
    ///      back when the addresses were configured at `initialize`. Phase-3
    ///      review HIGH #6 fix replaces `IOracleAnchor.isKnownRoot` with a
    ///      freshness check that the deployed (immutable, non-upgradeable)
    ///      anchors don't expose — so we must redeploy them, but the proxy
    ///      had no admin path to repoint these. Solution: bake new anchor
    ///      addresses into the impl bytecode as constructor immutables
    ///      (`priceAnchor`/`yieldAnchor` below). These slots stay reserved
    ///      so existing proxies keep their layout but the values are dead.
    ///      `initialize` continues to populate them so cross-impl readers
    ///      that haven't migrated still see a non-zero value, but the
    ///      execute path reads the immutable.
    address private _priceAnchorDeprecated;
    address private _yieldAnchorDeprecated;

    /// @dev O(1) universe-membership lookup populated at `initialize`.
    ///      Replaces a linear scan over `_manifest.assetUniverse` that ran
    ///      every trade (`_runSwapTrades` checks each `Call.target`). At
    ///      `assetUniverse.length == 4` the scan was ~2.1k gas/call;
    ///      mapping lookup is ~2.1k cheaper. phase2-review.md item 19.
    mapping(address asset => bool isUniverse) internal _universeAsset;

    // ── WS-CX-2 / Phase 4 — NAV-divergence one-sided cash-floor check ─
    //
    // Spec: Helios.md §6.4 (rewritten 2026-05-07). Fires when a signed
    // `reportNAV` falls below `baseAsset.balanceOf(this)` by more than
    // `navDivergenceThresholdBps` for two consecutive snapshots —
    // unambiguous evidence of operator under-reporting under the
    // long-only spot invariant `NAV ≥ cashHeld`.

    /// @notice Override for `NAV_DIVERGENCE_THRESHOLD_BPS_DEFAULT`.
    ///         Owner-tunable; `0` means "use default". Set via
    ///         `setNavDivergenceThresholdBps`.
    uint16 public navDivergenceThresholdBps;
    /// @notice Counter of *consecutive* breaching `reportNAV` calls.
    ///         Resets to 0 on any non-breaching report (signedNAV ≥
    ///         markedFloor or divergence < threshold).
    uint8 public consecutiveNavDivergenceBreaches;

    /// @dev Reserved storage for future upgrades. Append new state variables
    ///      ABOVE this gap and shrink it accordingly so storage layout stays
    ///      compatible. WS-CX-2 used 1 of the prior 47 slots:
    ///      `navDivergenceThresholdBps` + `consecutiveNavDivergenceBreaches`
    ///      pack into the same slot (16 + 8 = 24 bits).
    uint256[46] private __gap;

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
    error NavExceedsCap();
    error NavTooOld();
    error NotOperatorOrNavOracle();
    error OracleRootStale();
    error WithdrawExceedsNAVShare();
    error TradeCallFailed(uint256 index);
    error UnknownOracleRoot();
    error UnknownYieldOracleRoot();
    error AllowlistRootMismatch();
    error ParamsHashNotCommitted();

    /// @dev Selector for `IERC20.approve(address,uint256)`. Hardcoded so the
    ///      whitelist is independent of compile-time IERC20 metadata changes.
    bytes4 internal constant _APPROVE_SELECTOR = IERC20.approve.selector;

    /// @notice Maximum age of an oracle root the proof's `oracle_root`
    ///         input may reference, measured against `block.timestamp`
    ///         at trade execution. 180s matches `Helios.md` §10's
    ///         freshness budget — the off-chain oracle commits a fresh
    ///         root every 60s so a healthy chain has at least three
    ///         valid candidates at any given time. HIGH #6 in
    ///         `docs/phase-3-review.md`.
    uint256 internal constant _MAX_ORACLE_STALENESS_SEC = 180;

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

    /// @notice Anchors that authenticate `oracle_root` / `yield_oracle_root`
    ///         public inputs. Without these the prover can mint a Poseidon
    ///         root over fictitious prices and pass the verifier — Helios.md
    ///         §9.3 requires the trade's oracle root be one the off-chain
    ///         oracle has actually attested. Baked into the impl at deploy
    ///         time so a UUPS upgrade can repoint the proxy at fresh anchors
    ///         (Phase-3 HIGH #6, `docs/phase-3-deploy-plan.md` Unit 2).
    address public immutable priceAnchor;
    address public immutable yieldAnchor;

    /// @custom:oz-upgrades-unsafe-allow constructor
    /// @custom:oz-upgrades-unsafe-allow state-variable-immutable
    constructor(address priceAnchor_, address yieldAnchor_) {
        if (priceAnchor_ == address(0) || yieldAnchor_ == address(0)) revert ZeroAddress();
        priceAnchor = priceAnchor_;
        yieldAnchor = yieldAnchor_;
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
        __Pausable_init();

        _manifest = p.manifest;
        baseAsset = p.baseAsset;
        registry = p.registry;
        verifier = p.verifier;
        allowedRouter = p.allowedRouter;
        navOracle = p.navOracle;
        allocatorVault = p.allocatorVault;
        // Write the InitParams anchor addresses to the deprecated slots so
        // any external reader still sees a non-zero value during transition.
        // The execute path uses the constructor immutables — the impl's
        // `priceAnchor()` / `yieldAnchor()` getters return those, not these.
        _priceAnchorDeprecated = p.priceAnchor;
        _yieldAnchorDeprecated = p.yieldAnchor;

        // PR5 (item 19): populate the universe-membership mapping once at
        // init so per-trade calldata binding is an O(1) sload instead of
        // walking the array every call.
        for (uint256 i = 0; i < p.manifest.assetUniverse.length; i++) {
            _universeAsset[p.manifest.assetUniverse[i]] = true;
        }
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

    /// @notice Owner-only emergency stop. Halts new allocations + trade
    ///         execution. Defunds (`withdrawToAllocator`,
    ///         `distributeRealized`) remain open so the AllocatorVault
    ///         can rescue capital. NAV reporting also stays open so the
    ///         on-chain NAV doesn't go stale during the halt.
    ///         HIGH #10 in `docs/phase-3-review.md`.
    function pause() external onlyOwner {
        _pause();
    }

    function unpause() external onlyOwner {
        _unpause();
    }

    // ── Capital flow (allocator vault entry/exit) ───────────────────

    /// @notice Pull base-asset capital in from the paired allocator vault.
    function allocateFrom(uint256 amount)
        external
        onlyAllocatorVault
        notHalted
        whenNotPaused
        nonReentrant
    {
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
        // HIGH #8 in `docs/phase-3-review.md` — cap withdraw at the
        // allocator's prorated NAV share. Previously the contract clamped
        // `_totalNAV` to 0 and let the caller drain up to its principal,
        // which under multi-allocator state lets one allocator drain past
        // its fair share when the strategy is in unrealized loss; the
        // asset-balance check would then revert *for the next allocator*
        // instead of the over-drawer. Refusing the over-pull at source
        // forces the AllocatorVault to request `min(principal, navShare)`
        // — see `_unwindAndCredit`.
        if (amount > _allocationOf[allocator]) revert AllocationOverdrawn();
        if (amount > _navOf(allocator)) revert WithdrawExceedsNAVShare();
        _allocationOf[allocator] -= amount;
        _totalNAV -= amount;
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
    ) external onlyOperator notHalted whenNotPaused nonReentrant {
        _validateAndVerify(proof, publicInputs);
        _runSwapTrades(publicInputs, trades);
        _emitTradeAttested(publicInputs);
    }

    /// @notice yield_rotation_v1 entry path. The 13-PI layout omits asset
    ///         indices (rotation is whole-position; the allocator picks
    ///         the destination market) but binds the same hardening
    ///         fields as the swap path: vault address, params hash, the
    ///         registry's markets allowlist root, and now the
    ///         block-window [start, end] interval (review followup #5).
    ///         Private witnesses bound by the circuit but not visible
    ///         on chain:
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
    ) external onlyOperator notHalted whenNotPaused nonReentrant {
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
        // but not for one the protocol has signed off on. The freshness
        // gate refuses roots older than `_MAX_ORACLE_STALENESS_SEC` so a
        // months-old committed root cannot retroactively justify a trade
        // (HIGH #6 in `docs/phase-3-review.md`).
        {
            uint64 committedAt =
                IOracleAnchor(priceAnchor).freshness(bytes32(publicInputs[PI_ORACLE_ROOT]));
            if (committedAt == 0) revert UnknownOracleRoot();
            if (block.timestamp > uint256(committedAt) + _MAX_ORACLE_STALENESS_SEC) {
                revert OracleRootStale();
            }
        }

        bytes32 tradeHash = bytes32(publicInputs[PI_TRADE_HASH]);
        if (_seenTradeHash[tradeHash]) revert TradeAlreadySettled();
        _seenTradeHash[tradeHash] = true;

        if (!ITradeAttestationVerifier(verifier)
                .verify(_manifest.declaredClass, proof, publicInputs)) {
            revert InvalidProof();
        }
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
        if (block.number < publicInputs[PI_YR_BLOCK_WINDOW_START]) revert WindowNotStarted();
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
                .verify(_manifest.declaredClass, proof, publicInputs)) {
            revert InvalidProof();
        }
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
            uint64(publicInputs[PI_YR_BLOCK_WINDOW_START]),
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

    /// @notice Maximum age of a `reportNAV` signature relative to
    ///         `block.timestamp`. The monotonicity check on
    ///         `lastNAVTimestamp` prevents replay of *older-than-current*
    ///         signatures, but doesn't bound how old a never-applied
    ///         signature can be — without this gate, a navOracle key
    ///         compromised at T+N can submit any signature signed during
    ///         [last_post, T+N). 600s is wide enough to absorb mempool
    ///         delays, narrow enough that a key rotation is the de-facto
    ///         expiry. HIGH #7 in `docs/phase-3-review.md`.
    uint256 internal constant _MAX_NAV_AGE_SEC = 600;

    /// @notice Default below-cash-floor divergence threshold for
    ///         `reportNAV`. 5% (500 bps) per Helios.md §6.4 — wider
    ///         than typical legitimate intra-bar swap-in-flight noise,
    ///         tighter than sustained operator dishonesty. Override
    ///         via owner-only `setNavDivergenceThresholdBps`.
    ///         `NavDivergenceObserved` and `NavDivergenceThresholdUpdated`
    ///         are declared on `IStrategyVault` so the auto-generated
    ///         ABI bindings expose them to downstream services.
    uint16 internal constant _NAV_DIVERGENCE_THRESHOLD_BPS_DEFAULT = 500;

    function setNavDivergenceThresholdBps(uint16 bps) external onlyOwner {
        emit NavDivergenceThresholdUpdated(navDivergenceThresholdBps, bps);
        navDivergenceThresholdBps = bps;
    }

    function _effectiveNavDivergenceThresholdBps() internal view returns (uint16) {
        uint16 v = navDivergenceThresholdBps;
        return v == 0 ? _NAV_DIVERGENCE_THRESHOLD_BPS_DEFAULT : v;
    }

    /// @notice Apply an off-chain NAV snapshot signed by `navOracle`.
    /// @dev signedNAV = abi.encode(uint256 totalNAV, uint64 timestamp, bytes signature).
    ///      The signature is EIP-712 typed-data over
    ///      `NAVUpdate(uint256 totalNAV, uint64 timestamp)` under the domain
    ///      `(HeliosStrategyVault, "1", chainId, verifyingContract)`. The
    ///      domain pins the digest to (a) this chain and (b) this vault, so
    ///      a navOracle signature cannot be replayed against a sibling vault
    ///      or onto a different chain. The pre-Phase-2 raw-digest format is
    ///      unsupported — signers must produce typed-data signatures.
    ///
    ///      Caller-restricted: only the strategy operator or the navOracle
    ///      itself may submit. Auth is also enforced cryptographically by
    ///      the signature recovery, but the caller restriction prevents
    ///      MEV-bots from front-running legitimate operator submissions
    ///      with stale-but-valid signatures (HIGH #7).
    function reportNAV(bytes calldata signedNAV) external {
        if (msg.sender != _manifest.operator && msg.sender != navOracle) {
            revert NotOperatorOrNavOracle();
        }
        (uint256 totalNAV_, uint64 timestamp, bytes memory signature) =
            abi.decode(signedNAV, (uint256, uint64, bytes));
        if (timestamp <= lastNAVTimestamp) revert StaleNav();
        // Bounded replay window: refuse signatures older than
        // `_MAX_NAV_AGE_SEC` even though they pass the monotonicity check.
        // This caps how far back a never-applied signature can reach when
        // the navOracle key is rotated or compromised.
        if (block.timestamp > timestamp + _MAX_NAV_AGE_SEC) revert NavTooOld();
        // Cap NAV at 10× the manifest's maxCapacity. Without this cap, a
        // compromised navOracle could set _totalNAV near 2^256, after which
        // every read of _navOf overflows in `_totalNAV * _allocationOf[..]`,
        // permanently DoS'ing reads on this vault. 10× leaves plenty of
        // headroom for legitimate gain reporting (Helios.md §6.4 caps strategy
        // returns well below this) while bounding the attack surface.
        if (totalNAV_ > 10 * _manifest.maxCapacity) revert NavExceedsCap();
        bytes32 structHash = keccak256(abi.encode(_NAV_UPDATE_TYPEHASH, totalNAV_, timestamp));
        bytes32 digest = _hashTypedDataV4(structHash);
        address signer = ECDSA.recover(digest, signature);
        if (signer != navOracle) revert NavSignatureInvalid();

        _totalNAV = totalNAV_;
        lastNAVTimestamp = timestamp;
        emit NAVReported(address(this), totalNAV_, timestamp);

        _checkNavDivergence(totalNAV_, timestamp);
    }

    /// @dev v1 one-sided cash-floor NAV-divergence check. The long-only
    ///      spot strategy classes satisfy `NAV ≥ cashHeld` (you cannot
    ///      lose more than you have), so a signed NAV below
    ///      `baseAsset.balanceOf(this)` by more than the threshold is
    ///      unambiguous evidence of operator under-reporting.
    ///      Bidirectional checks (operator over-reports during a real
    ///      drawdown) need an upper-bound NAV recomputation against an
    ///      on-chain price source; that lands in v2 alongside the
    ///      per-asset TWAP anchor (Helios.md §6.4 + §17 Phase 1).
    function _checkNavDivergence(uint256 signedNAV, uint64 snapshotNonce) internal {
        uint256 markedFloor = baseAsset.balanceOf(address(this));
        // No cash held → no lower bound to enforce. Reset counter so a
        // freshly-funded vault that goes through cash → zero → cash
        // doesn't carry stale breach state across the gap.
        if (markedFloor == 0) {
            consecutiveNavDivergenceBreaches = 0;
            return;
        }
        // signedNAV ≥ cashHeld is consistent with NAV ≥ cashHeld; the
        // operator is reporting *at least* the cash floor, which is
        // honest under the long-only invariant.
        if (signedNAV >= markedFloor) {
            consecutiveNavDivergenceBreaches = 0;
            return;
        }
        // Below the floor. Compute divergence vs the floor — denominator
        // is the floor (not the signed value) so the threshold scales
        // with cash held, not with the lie itself.
        uint256 diff = markedFloor - signedNAV;
        uint256 divergenceBps = (diff * 10_000) / markedFloor;
        if (divergenceBps <= uint256(_effectiveNavDivergenceThresholdBps())) {
            // Below floor but within tolerance. Don't accumulate — minor
            // drift (in-flight settlement, rounding) shouldn't slash.
            consecutiveNavDivergenceBreaches = 0;
            return;
        }
        uint8 next = consecutiveNavDivergenceBreaches + 1;
        consecutiveNavDivergenceBreaches = next;
        if (next >= 2) {
            emit NavDivergenceObserved(address(this), signedNAV, markedFloor, snapshotNonce);
        }
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

    /// @notice The currently-binding params hash. The registry-committed
    ///         value is the canonical source: operators MUST call
    ///         `StrategyRegistry.commitInitialParamsHash` after
    ///         `registerStrategy` and before the vault attempts its first
    ///         trade. Reverts otherwise. The earlier manifest fallback
    ///         meant a strategy could trade indefinitely against
    ///         `_manifest.paramsHash` while never engaging the rotation
    ///         flow — phase2-review.md item 12.
    function _activeParamsHash() internal view returns (bytes32) {
        bytes32 fromRegistry = IStrategyRegistry(registry).paramsHashOf(address(this));
        if (fromRegistry == bytes32(0)) revert ParamsHashNotCommitted();
        return fromRegistry;
    }

    function _navOf(address allocator) internal view returns (uint256) {
        // Phase 1: single allocator vault, so totalAllocated == _allocationOf[allocatorVault].
        uint256 totalAlloc = _allocationOf[allocatorVault];
        if (totalAlloc == 0) return 0;
        return (_totalNAV * _allocationOf[allocator]) / totalAlloc;
    }

    function _isUniverseAsset(address target) internal view returns (bool) {
        return _universeAsset[target];
    }
}
