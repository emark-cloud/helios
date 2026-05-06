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

    /// @dev Reserved storage for future upgrades. Append new state variables
    ///      ABOVE this gap and shrink it accordingly so storage layout stays compatible.
    uint256[48] private __gap;

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
        if (rec.defundedAt != 0) revert AllocationDefunded();

        _checkStrategyRegistered(strategy);
        _checkMetaStrategyBounds(user, strategy, amount);

        // Pull capital from the user vault then push into the strategy.
        IUserVaultForAllocator(userVault).transferToAllocator(user, amount);
        baseAsset.forceApprove(strategy, amount);
        IStrategyVault(strategy).allocateFrom(amount);

        bool isNew = rec.strategy == address(0);
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

    function defundStrategy(address user, address strategy, string calldata reason)
        external
        nonReentrant
    {
        AllocationRecord storage rec = _allocations[user][strategy];
        if (rec.strategy == address(0)) revert StrategyNotAllocated();
        if (rec.defundedAt != 0) revert AllocationDefunded();

        bool permissionless = msg.sender != operator;
        if (permissionless) {
            // Anyone can defund a position whose drawdown breaches the user's
            // meta-strategy threshold. Compute strategy's NAV-share for this
            // allocator vault, prorated to the user's capitalDeployed.
            uint256 nav = IStrategyVault(strategy).navOf(address(this));
            uint256 alloc = IStrategyVault(strategy).allocationOf(address(this));
            uint256 userShare = alloc == 0 ? 0 : (nav * rec.capitalDeployed) / alloc;
            uint256 hwm = rec.strategyHighWaterMark;
            uint256 ddBps = hwm == 0 || userShare >= hwm ? 0 : ((hwm - userShare) * 10_000) / hwm;
            uint256 thresholdBps =
                IUserVaultForAllocator(userVault).metaStrategyOf(user).drawdownThresholdBps;
            if (ddBps < thresholdBps) revert DrawdownNotBreached();
        }

        _unwindAndCredit(user, strategy);
        rec.defundedAt = uint64(block.timestamp);

        emit StrategyDefunded(user, strategy, reason, msg.sender);
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
        if (rec.defundedAt != 0) revert AllocationDefunded();
        _checkStrategyRegistered(strategy);
        _checkMetaStrategyBounds(user, strategy, amount);

        IUserVaultForAllocator(userVault).transferToAllocator(user, amount);
        baseAsset.forceApprove(strategy, amount);
        IStrategyVault(strategy).allocateFrom(amount);

        bool isNew = rec.strategy == address(0);
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
}
