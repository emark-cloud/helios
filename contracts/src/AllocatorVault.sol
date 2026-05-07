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
    PausableUpgradeable
} from "@openzeppelin/contracts-upgradeable/utils/PausableUpgradeable.sol";
import {
    ReentrancyGuardTransient
} from "@openzeppelin/contracts/utils/ReentrancyGuardTransient.sol";
import { IERC20 } from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import { SafeERC20 } from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

import { IAllocatorVault } from "./interfaces/IAllocatorVault.sol";
import { IStrategyVault } from "./interfaces/IStrategyVault.sol";
import { IStrategyRegistry } from "./interfaces/IStrategyRegistry.sol";
import { IOracleAnchor } from "./interfaces/IOracleAnchor.sol";
import { MetaStrategyLib } from "./interfaces/IMetaStrategy.sol";

/// @notice Slim view onto UserVault. AllocatorVault uses these privileged
///         methods to move capital while UserVault enforces the meta-strategy
///         and the user→allocator delegation.
interface IUserVaultForAllocator {
    function transferToAllocator(address user, uint256 amount) external;
    function creditFromAllocator(address user, uint256 amount) external;
    function metaStrategyOf(address user)
        external
        view
        returns (MetaStrategyLib.MetaStrategy memory);
    function isClassAllowedFor(address user, bytes32 classId) external view returns (bool);
    function allocatorOf(address user) external view returns (address);
}

/// @title AllocatorVault
/// @notice Per-allocator working capital + per-strategy allocations.
///         Phase 1 simplification: one operator EOA (or multisig) drives all
///         allocate/rebalance/settle calls; defund becomes permissionless when
///         the user's meta-strategy drawdown threshold is breached.
///         Helios.md §6.3.
contract AllocatorVault is
    IAllocatorVault,
    Initializable,
    OwnableUpgradeable,
    PausableUpgradeable,
    ReentrancyGuardTransient,
    UUPSUpgradeable
{
    using SafeERC20 for IERC20;

    IERC20 public baseAsset;
    address public operator; // EOA / multisig that drives the allocator service
    address public userVault;
    address public strategyRegistry;
    uint16 public allocatorFeeRateBps; // skim from realized PnL forwarded to operator
    uint32 public chainId; // home chain id, snapshotted at init

    mapping(address user => mapping(address strategy => AllocationRecord)) internal _allocations;
    /// @dev Mirror of `_allocations[user][s].capitalDeployed` retained for
    ///      UUPS storage-layout compatibility. Writes were removed in
    ///      phase2-review.md item 19 — every prior reader/writer points at
    ///      the canonical struct field instead. Saves an SSTORE per
    ///      allocate / rebalance / defund (~5k gas / strategy / call).
    ///      The slot stays so existing proxies can be upgraded without
    ///      shifting the layout; new deployments will leave it empty.
    mapping(address user => mapping(address strategy => uint256)) internal
        _strategyDeployed_deprecated;
    uint256 internal _accruedFees;

    /// @dev Sum of `_allocations[user][*].capitalDeployed` over all *active*
    ///      (non-defunded) strategies. Maintained at allocate/rebalance/defund
    ///      so `_checkMetaStrategyBounds` can enforce `meta.maxCapital` in O(1).
    mapping(address user => uint256) internal _userTotalDeployed;
    /// @dev Count of *active* (non-defunded) strategies a user is allocated
    ///      across. Decremented on first defund, incremented on first allocate.
    ///      Drives `meta.maxStrategiesCount` enforcement.
    mapping(address user => uint256) internal _userActiveStrategyCount;

    /// @dev Last timestamp at which `rebalance` succeeded for a user.
    ///      Read at the top of `rebalance` against
    ///      `meta.rebalanceCadenceSec` so a single user cannot rebalance
    ///      faster than the cadence they signed (MEDIUM in
    ///      `docs/phase-3-review.md`). Initial rebalance is never rejected
    ///      (last == 0). `allocateToStrategy` does not advance this clock —
    ///      cadence governs rebalances only, not first-time allocations.
    mapping(address user => uint64) internal _userLastRebalanceTimestamp;

    // ── WS-CX-1 / Phase 4 — caller-cadence permissionless defund ────
    //
    // Spec: Helios.md §6.3 (rewritten 2026-05-07). Implementation notes
    // and design rationale: docs/phase4-plan.md §4.1.

    /// @notice Oracle anchor read for the "is the oracle online" gate
    ///         on the first observation of a pending defund. Address
    ///         zero disables the gate (pre-set state) — calls revert
    ///         `OracleAnchorNotSet`. Set via `setOracleAnchor`.
    address public oracleAnchor;
    /// @notice Reward cap (USDC e6 units) paid from strategy stake on a
    ///         successful permissionless finalize. Default 500_000_000
    ///         (= $500). Owner-tunable.
    uint128 public defundRewardCapUsdE6;
    /// @dev Per-(user,strategy) pending defund state. Cleared on
    ///      finalize / cancel / recovery. Reads via `pendingDefundOf`.
    mapping(address user => mapping(address strategy => PendingDefund)) internal _pendingDefunds;

    /// @dev Reserved storage for future upgrades. Append new state variables
    ///      ABOVE this gap and shrink it accordingly so storage layout stays compatible.
    ///      WS-CX-1 used 3 of the prior 47 slots: oracleAnchor (1),
    ///      defundRewardCapUsdE6 (1), _pendingDefunds (1).
    uint256[44] private __gap;

    /// @dev Minimum block spacing between two consecutive observations
    ///      of the same pending defund. Caller-cadence "bars" — at
    ///      Kite's 1s blocks, 300 ≈ 5 min, matching the spec's
    ///      "5-minute oracle TWAP snapshot" cadence in §6.3.
    uint256 internal constant MIN_BAR_BLOCKS = 300;
    /// @dev Maximum age of `OraclePriceAnchor.latest().committedAt` for
    ///      the first observation of a pending entry. 180s matches the
    ///      proof-side staleness window in `Helios.md §6.10`.
    uint256 internal constant MAX_STALENESS_SEC = 180;
    /// @dev Default reward cap if `setDefundRewardCap` has not been
    ///      called post-upgrade. $500 in USDC e6 units.
    uint128 internal constant DEFAULT_REWARD_CAP_USD_E6 = 500 * 1e6;
    /// @dev `keccak256("RECOVERED")` — `DefundCancelled` reason when
    ///      drawdown recovered above threshold mid-observation.
    bytes32 internal constant CANCEL_REASON_RECOVERED = keccak256("RECOVERED");
    /// @dev `keccak256("OPERATOR_CANCEL")` — operator override.
    bytes32 internal constant CANCEL_REASON_OPERATOR = keccak256("OPERATOR_CANCEL");

    error ZeroAddress();
    error ZeroAmount();
    error InvalidWeights();
    error LengthMismatch();
    error StrategyAlreadyAllocated();
    error StrategyNotAllocated();
    error AllocationDefunded();
    error StrategyNotRegistered();
    error StrategyInactive();
    error MetaCapacityExceeded();
    error MetaPerStrategyExceeded();
    error MetaMaxStrategiesExceeded();
    error MetaClassNotAllowed();
    error MetaExpired();
    error NoAccruedFees();
    error NotOperatorOrPermissionless();
    error RebalanceTooSoon();

    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }

    function initialize(
        IERC20 baseAsset_,
        address operator_,
        address userVault_,
        address strategyRegistry_,
        uint16 allocatorFeeRateBps_,
        address owner_
    ) external initializer {
        if (
            address(baseAsset_) == address(0) || operator_ == address(0) || userVault_ == address(0)
                || strategyRegistry_ == address(0) || owner_ == address(0)
        ) revert ZeroAddress();

        __Ownable_init(owner_);
        __Pausable_init();
        baseAsset = baseAsset_;
        operator = operator_;
        userVault = userVault_;
        strategyRegistry = strategyRegistry_;
        allocatorFeeRateBps = allocatorFeeRateBps_;
        chainId = uint32(block.chainid);
    }

    function _authorizeUpgrade(address) internal override onlyOwner { }

    /// @notice Owner-only emergency stop. Halts new allocations,
    ///         rebalance, and fee settlement. Defunds remain open so
    ///         users / operators can rescue capital. HIGH #10 in
    ///         `docs/phase-3-review.md`.
    function pause() external onlyOwner {
        _pause();
    }

    function unpause() external onlyOwner {
        _unpause();
    }

    /// @notice Wire (or rotate) the oracle anchor read by the
    ///         permissionless defund freshness gate. Owner-only.
    ///         Setting to address(0) disables the gate by reverting
    ///         every `triggerDefund` with `OracleAnchorNotSet`.
    function setOracleAnchor(address anchor_) external onlyOwner {
        emit OracleAnchorUpdated(oracleAnchor, anchor_);
        oracleAnchor = anchor_;
    }

    /// @notice Tune the reward cap paid out of strategy stake on a
    ///         successful permissionless finalize. Owner-only. Pass
    ///         `capE6 = 0` to fall back to `DEFAULT_REWARD_CAP_USD_E6`
    ///         (= $500 USDC). Stored as `uint128` so per-defund math
    ///         stays cheap.
    function setDefundRewardCap(uint128 capE6) external onlyOwner {
        emit DefundRewardCapUpdated(defundRewardCapUsdE6, capE6);
        defundRewardCapUsdE6 = capE6;
    }

    /// @dev Effective cap, falling back to the default when the
    ///      owner has not yet set one (post-upgrade state). All
    ///      `min(...)` math on the finalize path reads through here.
    function _effectiveRewardCapE6() internal view returns (uint128) {
        uint128 c = defundRewardCapUsdE6;
        return c == 0 ? DEFAULT_REWARD_CAP_USD_E6 : c;
    }

    modifier onlyOperator() {
        if (msg.sender != operator) revert NotAllocator();
        _;
    }

    // ── Allocation flow ─────────────────────────────────────────────

    function allocateToStrategy(address user, address strategy, uint256 amount)
        external
        onlyOperator
        nonReentrant
        whenNotPaused
    {
        if (amount == 0) revert ZeroAmount();

        AllocationRecord storage rec = _allocations[user][strategy];
        // MEDIUM in `docs/phase-3-review.md`: a defunded slot was
        // permanently blocked from re-allocation. Once `_unwindAndCredit`
        // has zeroed `capitalDeployed`, the slot has no live capital and
        // can be reopened with a fresh HWM. The defund event survives in
        // the event log; the slot is treated as a new lifecycle from the
        // subgraph's point of view (we re-emit `AllocationCreated` below).
        bool reopening;
        if (rec.defundedAt != 0) {
            if (rec.capitalDeployed != 0) revert AllocationDefunded();
            reopening = true;
            rec.defundedAt = 0;
            rec.strategyHighWaterMark = 0;
        }

        _checkStrategyRegistered(strategy);
        _checkMetaStrategyBounds(user, strategy, amount);

        // Pull capital from the user vault then push into the strategy.
        IUserVaultForAllocator(userVault).transferToAllocator(user, amount);
        baseAsset.forceApprove(strategy, amount);
        IStrategyVault(strategy).allocateFrom(amount);

        bool isNew = rec.strategy == address(0) || reopening;
        rec.strategy = strategy;
        rec.capitalDeployed += amount;
        rec.strategyHighWaterMark = _maxU256(rec.strategyHighWaterMark, rec.capitalDeployed);
        rec.lastRebalanceTimestamp = uint64(block.timestamp);

        _userTotalDeployed[user] += amount;
        if (isNew) _userActiveStrategyCount[user] += 1;

        if (isNew) {
            emit AllocationCreated(user, strategy, amount, chainId);
        } else {
            emit AllocationIncreased(user, strategy, amount);
        }
    }

    /// @notice Operator-only single-shot defund. Permissionless callers
    ///         use the `triggerDefund` / `finalizeDefund` pair below
    ///         which enforces persistence + bond + confirm window per
    ///         `Helios.md §6.3` (Phase 4).
    /// @dev    If a permissionless trigger is mid-flight when the
    ///         operator calls this, the pending entry is cleared and
    ///         the bond is refunded to the triggerer — equivalent to
    ///         calling `cancelDefund` first. We fold it inline so the
    ///         operator's defund is always a single tx.
    function defundStrategy(address user, address strategy, string calldata reason)
        external
        onlyOperator
        nonReentrant
    {
        AllocationRecord storage rec = _allocations[user][strategy];
        if (rec.strategy == address(0)) revert StrategyNotAllocated();
        if (rec.defundedAt != 0) revert AllocationDefunded();

        PendingDefund storage pending = _pendingDefunds[user][strategy];
        if (pending.breachCount != 0) {
            _refundBond(pending);
            delete _pendingDefunds[user][strategy];
            emit DefundCancelled(user, strategy, CANCEL_REASON_OPERATOR);
        }

        _unwindAndCredit(user, strategy);
        rec.defundedAt = uint64(block.timestamp);

        emit StrategyDefunded(user, strategy, reason, msg.sender);
    }

    // ── WS-CX-1 / Phase 4 — caller-cadence permissionless defund ────

    /// @notice Permissionless defund — one observation per call.
    ///         First call posts the bond and records the pending entry;
    ///         subsequent calls advance `breachCount` (must be spaced
    ///         ≥ `MIN_BAR_BLOCKS` apart) or clear the entry on a
    ///         non-breaching observation (refunding the bond).
    /// @dev    Spec: `Helios.md §6.3` (rewritten 2026-05-07);
    ///         design notes: `docs/phase4-plan.md §4.1`.
    function triggerDefund(address user, address strategy) external nonReentrant {
        AllocationRecord storage rec = _allocations[user][strategy];
        if (rec.strategy == address(0)) revert StrategyNotAllocated();
        if (rec.defundedAt != 0) revert AllocationDefunded();

        MetaStrategyLib.MetaStrategy memory meta =
            IUserVaultForAllocator(userVault).metaStrategyOf(user);
        uint256 ddBps = _observeDrawdownBps(strategy, rec);
        PendingDefund storage pending = _pendingDefunds[user][strategy];

        if (pending.breachCount == 0) {
            // First observation: gate on oracle freshness + drawdown
            // breach, then pull the bond and seed the pending entry.
            _checkOracleFresh();
            if (ddBps < uint256(meta.drawdownThresholdBps)) revert DrawdownNotBreached();

            uint128 bond = uint128((rec.capitalDeployed * uint256(meta.defundBondBps)) / 10_000);
            if (bond > 0) baseAsset.safeTransferFrom(msg.sender, address(this), bond);

            pending.firstObservedAt = uint64(block.timestamp);
            pending.firstObservedBlock = uint64(block.number);
            pending.lastObservedBlock = uint64(block.number);
            pending.breachCount = 1;
            pending.triggerer = msg.sender;
            pending.bondAmount = bond;

            emit DefundObserved(user, strategy, msg.sender, 1, ddBps, bond);
            // Single-bar persistence settings arm immediately (degenerate
            // but consistent — a meta-strategy with `defundTwapBars = 1`
            // wants a one-shot trigger).
            if (uint256(meta.defundTwapBars) <= 1) {
                emit DefundArmed(user, strategy, uint64(block.number));
            }
            return;
        }

        // Subsequent observation. Enforce bar spacing.
        if (block.number < uint256(pending.lastObservedBlock) + MIN_BAR_BLOCKS) {
            revert BarTooSoon();
        }

        if (ddBps < uint256(meta.drawdownThresholdBps)) {
            // Recovered. Refund the bond to whoever posted it and clear
            // the entry — caller-cadence design treats a non-breaching
            // observation as legitimate cancellation, not a slash.
            address triggerer = pending.triggerer;
            _refundBond(pending);
            delete _pendingDefunds[user][strategy];
            emit DefundCancelled(user, strategy, CANCEL_REASON_RECOVERED);
            // Surface the refund as the triggerer-side balance change so
            // off-chain accounting can tie the cancellation to the
            // (zero-amount) finalize sequence — keeps subgraph mappings
            // simple. Equivalent to `DefundFinalized(refunded=bond)` but
            // without the unwind.
            emit DefundFinalized(user, strategy, triggerer, pending.bondAmount, 0, 0);
            return;
        }

        uint8 nextCount = pending.breachCount + 1;
        pending.breachCount = nextCount;
        pending.lastObservedBlock = uint64(block.number);
        emit DefundObserved(user, strategy, pending.triggerer, nextCount, ddBps, 0);
        if (uint256(nextCount) == uint256(meta.defundTwapBars)) {
            emit DefundArmed(user, strategy, uint64(block.number));
        }
    }

    /// @notice Permissionless defund — finalize once armed and
    ///         `defundConfirmBlocks` have elapsed since the last
    ///         observation. Pays reward from `_accruedFees` (v1
    ///         deviation, see Helios.md §6.3) on confirmed breach;
    ///         slashes the bond to the user if NAV recovered.
    function finalizeDefund(address user, address strategy) external nonReentrant {
        AllocationRecord storage rec = _allocations[user][strategy];
        if (rec.strategy == address(0)) revert StrategyNotAllocated();
        if (rec.defundedAt != 0) revert AllocationDefunded();

        PendingDefund storage pending = _pendingDefunds[user][strategy];
        if (pending.breachCount == 0) revert DefundNotPending();

        MetaStrategyLib.MetaStrategy memory meta =
            IUserVaultForAllocator(userVault).metaStrategyOf(user);
        if (uint256(pending.breachCount) < uint256(meta.defundTwapBars)) {
            revert DefundNotArmed();
        }
        if (block.number < uint256(pending.lastObservedBlock) + uint256(meta.defundConfirmBlocks)) {
            revert ConfirmWindowNotElapsed();
        }

        uint256 ddBps = _observeDrawdownBps(strategy, rec);
        uint128 bond = pending.bondAmount;
        address triggerer = pending.triggerer;

        if (ddBps < uint256(meta.drawdownThresholdBps)) {
            // NAV recovered before finalize fired. Bond slashed to the
            // user's UserVault as compensation for the locked capital
            // (and as a small disincentive against speculative triggers
            // on transient drawdowns).
            delete _pendingDefunds[user][strategy];
            if (bond > 0) {
                baseAsset.forceApprove(userVault, bond);
                IUserVaultForAllocator(userVault).creditFromAllocator(user, bond);
            }
            emit DefundFinalized(user, strategy, triggerer, 0, 0, bond);
            return;
        }

        // Breach confirmed. Compute reward, then unwind. Reward source
        // is `_accruedFees` (v1 deviation — see Helios.md §6.3) capped
        // at `defundRewardCapUsdE6` and `defundBondBps × notional`.
        uint256 deployed = rec.capitalDeployed;
        uint256 cap = uint256(_effectiveRewardCapE6());
        uint256 rewardEligible = (deployed * uint256(meta.defundBondBps)) / 10_000;
        if (rewardEligible > cap) rewardEligible = cap;
        uint256 pool = _accruedFees;
        if (rewardEligible > pool) rewardEligible = pool;

        delete _pendingDefunds[user][strategy];

        // Debit the reward from the pool *before* unwinding so a
        // re-entrant strategy hook can't drain accruedFees and leave
        // us underwater. Pool is monotonic-decrement; unwind is
        // gated by `nonReentrant`.
        if (rewardEligible > 0) _accruedFees = pool - rewardEligible;

        _unwindAndCredit(user, strategy);
        rec.defundedAt = uint64(block.timestamp);

        if (bond > 0) baseAsset.safeTransfer(triggerer, bond);
        if (rewardEligible > 0) baseAsset.safeTransfer(triggerer, rewardEligible);

        emit StrategyDefunded(user, strategy, "DRAWDOWN_BREACH_FINALIZE", triggerer);
        emit DefundFinalized(user, strategy, triggerer, bond, rewardEligible, 0);
    }

    /// @notice Operator override — clears a pending defund entry and
    ///         refunds the bond to the original triggerer. Use when
    ///         the operator wants to defund through the operator path
    ///         without ambiguity, or when the trigger fired on a
    ///         drawdown the operator already addressed off-chain.
    function cancelDefund(address user, address strategy) external onlyOperator nonReentrant {
        PendingDefund storage pending = _pendingDefunds[user][strategy];
        if (pending.breachCount == 0) revert DefundNotPending();
        _refundBond(pending);
        delete _pendingDefunds[user][strategy];
        emit DefundCancelled(user, strategy, CANCEL_REASON_OPERATOR);
    }

    function rebalance(address user, address[] calldata strategies, uint256[] calldata weightsBps)
        external
        onlyOperator
        nonReentrant
        whenNotPaused
    {
        if (strategies.length != weightsBps.length || strategies.length == 0) {
            revert LengthMismatch();
        }

        // MEDIUM in `docs/phase-3-review.md`: enforce
        // `meta.rebalanceCadenceSec` so a runaway operator cannot
        // rebalance every block. First rebalance is always allowed
        // (last == 0); cadence == 0 disables the throttle entirely.
        uint256 cadence = IUserVaultForAllocator(userVault).metaStrategyOf(user).rebalanceCadenceSec;
        uint64 last = _userLastRebalanceTimestamp[user];
        if (cadence != 0 && last != 0 && block.timestamp < uint256(last) + cadence) {
            revert RebalanceTooSoon();
        }

        uint256 sum;
        uint256 totalDeployed;
        for (uint256 i = 0; i < strategies.length; i++) {
            sum += weightsBps[i];
            totalDeployed += _allocations[user][strategies[i]].capitalDeployed;
        }
        if (sum != 10_000) revert InvalidWeights();

        for (uint256 i = 0; i < strategies.length; i++) {
            address s = strategies[i];
            uint256 target = (totalDeployed * weightsBps[i]) / 10_000;
            uint256 current = _allocations[user][s].capitalDeployed;
            if (target > current) {
                _allocateInternal(user, s, target - current);
            } else if (target < current) {
                _withdrawPartial(user, s, current - target);
            }
            _allocations[user][s].lastRebalanceTimestamp = uint64(block.timestamp);
        }
        _userLastRebalanceTimestamp[user] = uint64(block.timestamp);
    }

    // ── Fee settlement ──────────────────────────────────────────────

    /// @dev Tight bundle of values that flow between `settleStrategyFee`
    ///      and `_settleFeeMath`. Returning a struct lets the helper
    ///      release the rest of its locals before the caller does the
    ///      transfers + storage write — keeps the no-viaIR build (used
    ///      by `forge coverage`) under the stack-too-deep limit.
    struct FeeSettlement {
        uint256 userRealized;
        uint256 stratFee;
        uint256 allocFee;
        uint256 leftover;
        uint256 newHwm;
    }

    function settleStrategyFee(address user, address strategy)
        external
        onlyOperator
        nonReentrant
        whenNotPaused
    {
        AllocationRecord storage rec = _allocations[user][strategy];
        if (rec.strategy == address(0)) revert StrategyNotAllocated();
        if (rec.defundedAt != 0) revert AllocationDefunded();

        // Pull realized PnL from the strategy (allocator-vault-wide).
        uint256 realizedTotal;
        {
            uint256 balBefore = baseAsset.balanceOf(address(this));
            IStrategyVault(strategy).distributeRealized(address(this));
            realizedTotal = baseAsset.balanceOf(address(this)) - balBefore;
        }
        if (realizedTotal == 0) {
            emit StrategyFeeSettled(user, strategy, 0, rec.strategyHighWaterMark);
            return;
        }

        // HIGH #4 — `_settleFeeMath` snapshots `userNavBefore` from the
        // strategy's pre-distribute NAV (read into the helper to keep
        // those locals off this stack). It HWM-gates the fee on
        // `excess = userNavBefore - prevHWM` so NAV round-trips through
        // the same range never re-charge fees, and bumps HWM only when
        // userNavBefore exceeds the prior peak.
        FeeSettlement memory s = _settleFeeMath(strategy, rec, realizedTotal);

        // Strategy fee → strategy operator.
        if (s.stratFee > 0) {
            baseAsset.safeTransfer(IStrategyVault(strategy).manifest().operator, s.stratFee);
        }
        // Allocator fee + dust → vault accrual.
        _accruedFees += s.allocFee + s.leftover;

        // Net user PnL → user vault.
        uint256 toUser = s.userRealized - s.stratFee - s.allocFee;
        if (toUser > 0) {
            baseAsset.forceApprove(userVault, toUser);
            IUserVaultForAllocator(userVault).creditFromAllocator(user, toUser);
        }

        rec.strategyHighWaterMark = s.newHwm;
        emit StrategyFeeSettled(user, strategy, s.stratFee, s.newHwm);
    }

    /// @dev Pure-ish settlement math, factored out of `settleStrategyFee`
    ///      for stack-depth reasons. Reads the strategy's pre-settle NAV
    ///      to anchor HWM and derive HWM-gated fees. Returns a
    ///      `FeeSettlement` struct that the caller uses for transfers +
    ///      storage write — no transfers happen here.
    function _settleFeeMath(address strategy, AllocationRecord storage rec, uint256 realizedTotal)
        internal
        view
        returns (FeeSettlement memory s)
    {
        // Pre-settle equity: NAV after `distributeRealized` already moved
        // `realizedTotal` out, so userNavBefore = (post-distribute NAV +
        // realizedTotal) prorated. Equivalent: the strategy's `navOf`
        // here is post-distribute; add back realized to recover the peak.
        uint256 totalAlloc = IStrategyVault(strategy).allocationOf(address(this));
        uint256 deployed = rec.capitalDeployed;
        uint256 userRealized =
            totalAlloc == 0 ? realizedTotal : (realizedTotal * deployed) / totalAlloc;
        uint256 userNavBefore;
        {
            uint256 navAfter = IStrategyVault(strategy).navOf(address(this));
            uint256 userNavAfter = totalAlloc == 0 ? 0 : (navAfter * deployed) / totalAlloc;
            userNavBefore = userNavAfter + userRealized;
        }

        uint256 prevHwm = rec.strategyHighWaterMark;
        uint256 excess = userNavBefore > prevHwm ? userNavBefore - prevHwm : 0;
        uint256 feeEligible = userRealized < excess ? userRealized : excess;

        uint16 stratFeeBps = IStrategyVault(strategy).manifest().feeRateBps;
        s.userRealized = userRealized;
        s.stratFee = (feeEligible * stratFeeBps) / 10_000;
        s.allocFee = (feeEligible * allocatorFeeRateBps) / 10_000;
        s.leftover = realizedTotal - userRealized;
        s.newHwm = userNavBefore > prevHwm ? userNavBefore : prevHwm;
    }

    function withdrawAllocatorFees() external onlyOperator nonReentrant {
        uint256 amount = _accruedFees;
        if (amount == 0) revert NoAccruedFees();
        _accruedFees = 0;
        baseAsset.safeTransfer(operator, amount);
        emit AllocatorFeesWithdrawn(operator, amount);
    }

    // ── Views ───────────────────────────────────────────────────────

    function allocationOf(address user, address strategy)
        external
        view
        returns (AllocationRecord memory)
    {
        return _allocations[user][strategy];
    }

    function pendingDefundOf(address user, address strategy)
        external
        view
        returns (PendingDefund memory)
    {
        return _pendingDefunds[user][strategy];
    }

    function accruedFees() external view returns (uint256) {
        return _accruedFees;
    }

    /// @notice Sum of capital actively deployed across all of `user`'s
    ///         non-defunded strategies. Read by `UserVault.setMetaStrategy`
    ///         to refuse tightening updates while the user has live
    ///         positions whose existing terms could be griefed (HIGH #5
    ///         in `docs/phase-3-review.md`).
    function userTotalDeployed(address user) external view returns (uint256) {
        return _userTotalDeployed[user];
    }

    // ── Internal ────────────────────────────────────────────────────

    function _allocateInternal(address user, address strategy, uint256 amount) internal {
        AllocationRecord storage rec = _allocations[user][strategy];
        // Mirror `allocateToStrategy`'s reopen-on-zero policy so a
        // rebalance that grows back into a previously-defunded slot is
        // also unblocked.
        bool reopening;
        if (rec.defundedAt != 0) {
            if (rec.capitalDeployed != 0) revert AllocationDefunded();
            reopening = true;
            rec.defundedAt = 0;
            rec.strategyHighWaterMark = 0;
        }
        _checkStrategyRegistered(strategy);
        _checkMetaStrategyBounds(user, strategy, amount);

        IUserVaultForAllocator(userVault).transferToAllocator(user, amount);
        baseAsset.forceApprove(strategy, amount);
        IStrategyVault(strategy).allocateFrom(amount);

        bool isNew = rec.strategy == address(0) || reopening;
        rec.strategy = strategy;
        rec.capitalDeployed += amount;
        rec.strategyHighWaterMark = _maxU256(rec.strategyHighWaterMark, rec.capitalDeployed);

        _userTotalDeployed[user] += amount;
        if (isNew) _userActiveStrategyCount[user] += 1;

        if (isNew) emit AllocationCreated(user, strategy, amount, chainId);
        else emit AllocationIncreased(user, strategy, amount);
    }

    function _withdrawPartial(address user, address strategy, uint256 amount) internal {
        AllocationRecord storage rec = _allocations[user][strategy];
        if (amount > rec.capitalDeployed) revert AllocationOutOfBounds();
        IStrategyVault(strategy).withdrawToAllocator(address(this), amount);
        rec.capitalDeployed -= amount;
        _userTotalDeployed[user] -= amount;
        baseAsset.forceApprove(userVault, amount);
        IUserVaultForAllocator(userVault).creditFromAllocator(user, amount);
        emit AllocationDecreased(user, strategy, amount);
    }

    function _unwindAndCredit(address user, address strategy) internal {
        AllocationRecord storage rec = _allocations[user][strategy];
        // First sweep realized PnL.
        uint256 balBefore = baseAsset.balanceOf(address(this));
        IStrategyVault(strategy).distributeRealized(address(this));
        uint256 realized = baseAsset.balanceOf(address(this)) - balBefore;

        // HIGH #8 — pull `min(principal, navShare)` so a position in
        // unrealized loss returns the recoverable amount instead of
        // reverting. `withdrawToAllocator` rejects amounts above the
        // allocator's NAV share at source; previously the strategy
        // clamped `_totalNAV` and let any allocator drain past its
        // share, griefing siblings. `_navOf(this)` is post-distribute
        // since `distributeRealized` above already moved any PnL out
        // — so it equals exactly the loss-floor on a draw-down position.
        uint256 principal = rec.capitalDeployed;
        uint256 navShare = IStrategyVault(strategy).navOf(address(this));
        uint256 toPull = principal < navShare ? principal : navShare;
        if (toPull > 0) {
            IStrategyVault(strategy).withdrawToAllocator(address(this), toPull);
        }
        if (principal > 0) {
            // `_userTotalDeployed` is denominated in the original
            // capital the user committed, not what came back. Decrement
            // by the full principal so caps recompute correctly even
            // when loss is realized at unwind.
            _userTotalDeployed[user] -= principal;
        }
        if (rec.strategy != address(0)) _userActiveStrategyCount[user] -= 1;

        rec.capitalDeployed = 0;

        // Credit user's recovered balance back (principal capped at
        // navShare + their share of realized PnL).
        uint256 totalBack = toPull + realized;
        if (totalBack > 0) {
            baseAsset.forceApprove(userVault, totalBack);
            IUserVaultForAllocator(userVault).creditFromAllocator(user, totalBack);
        }
    }

    function _checkStrategyRegistered(address strategy) internal view {
        IStrategyRegistry.StrategyEntry memory s =
            IStrategyRegistry(strategyRegistry).strategyOf(strategy);
        if (s.registeredAt == 0) revert StrategyNotRegistered();
        if (!s.active) revert StrategyInactive();
    }

    function _checkMetaStrategyBounds(address user, address strategy, uint256 newAmount)
        internal
        view
    {
        MetaStrategyLib.MetaStrategy memory meta =
            IUserVaultForAllocator(userVault).metaStrategyOf(user);
        if (meta.validUntil != 0 && block.timestamp > meta.validUntil) revert MetaExpired();

        AllocationRecord storage rec = _allocations[user][strategy];

        // Aggregate cap: total deployed across all active strategies + newAmount <= maxCapital
        if (_userTotalDeployed[user] + newAmount > meta.maxCapital) revert MetaCapacityExceeded();

        // Max-strategies cap: opening a new slot must not exceed meta.maxStrategiesCount.
        // A top-up to an existing active allocation does not consume a new slot.
        if (rec.strategy == address(0) || rec.defundedAt != 0) {
            if (_userActiveStrategyCount[user] + 1 > uint256(meta.maxStrategiesCount)) {
                revert MetaMaxStrategiesExceeded();
            }
        }

        // Per-strategy cap: capitalDeployed + newAmount <= maxCapital * maxPerStrategyBps / 10_000
        uint256 perStratCap = (uint256(meta.maxCapital) * meta.maxPerStrategyBps) / 10_000;
        uint256 prospective = rec.capitalDeployed + newAmount;
        if (prospective > perStratCap) revert MetaPerStrategyExceeded();

        // Class-allowed check — O(1) via UserVault's denormalized mapping
        // (populated at setMetaStrategy). The struct field is kept so
        // `metaStrategyOf` callers see the full set without a separate
        // call into the mapping.
        bytes32 declared = IStrategyVault(strategy).manifest().declaredClass;
        if (!IUserVaultForAllocator(userVault).isClassAllowedFor(user, declared)) {
            revert MetaClassNotAllowed();
        }
    }

    function _maxU256(uint256 a, uint256 b) internal pure returns (uint256) {
        return a > b ? a : b;
    }

    // ── WS-CX-1 / Phase 4 helpers ──────────────────────────────────

    /// @dev Per-user-prorated drawdown vs allocation HWM, in bps.
    ///      Reads `IStrategyVault.navOf(this) / allocationOf(this)` to
    ///      isolate the user's share of mark-to-market loss from
    ///      sibling allocators in the same vault.
    function _observeDrawdownBps(address strategy, AllocationRecord storage rec)
        internal
        view
        returns (uint256)
    {
        uint256 nav = IStrategyVault(strategy).navOf(address(this));
        uint256 alloc = IStrategyVault(strategy).allocationOf(address(this));
        uint256 userShare = alloc == 0 ? 0 : (nav * rec.capitalDeployed) / alloc;
        uint256 hwm = rec.strategyHighWaterMark;
        if (hwm == 0 || userShare >= hwm) return 0;
        return ((hwm - userShare) * 10_000) / hwm;
    }

    /// @dev "Is the oracle online?" gate. Phase 2 oracle commits
    ///      Poseidon roots only — there is no per-asset price feed —
    ///      so freshness is the only signal we can extract from the
    ///      anchor on-chain. An empty ledger is treated as stale so
    ///      a never-initialized vault can't be defund-griefed.
    function _checkOracleFresh() internal view {
        address anchor = oracleAnchor;
        if (anchor == address(0)) revert OracleAnchorNotSet();
        if (IOracleAnchor(anchor).commitCount() == 0) revert OracleStale();
        IOracleAnchor.Commit memory c = IOracleAnchor(anchor).latest();
        if (block.timestamp > uint256(c.committedAt) + MAX_STALENESS_SEC) {
            revert OracleStale();
        }
    }

    /// @dev Refund a posted bond to its original triggerer. No-op if
    ///      the bond was zero (degenerate `defundBondBps = 0` setting,
    ///      kept legal so users can opt out of the bond mechanism).
    function _refundBond(PendingDefund storage pending) internal {
        uint128 bond = pending.bondAmount;
        if (bond > 0) baseAsset.safeTransfer(pending.triggerer, bond);
    }
}
