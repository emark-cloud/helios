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
        baseAsset = baseAsset_;
        operator = operator_;
        userVault = userVault_;
        strategyRegistry = strategyRegistry_;
        allocatorFeeRateBps = allocatorFeeRateBps_;
        chainId = uint32(block.chainid);
    }

    function _authorizeUpgrade(address) internal override onlyOwner { }

    modifier onlyOperator() {
        if (msg.sender != operator) revert NotAllocator();
        _;
    }

    // ── Allocation flow ─────────────────────────────────────────────

    function allocateToStrategy(address user, address strategy, uint256 amount)
        external
        onlyOperator
        nonReentrant
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

    function settleStrategyFee(address user, address strategy) external nonReentrant {
        AllocationRecord storage rec = _allocations[user][strategy];
        if (rec.strategy == address(0)) revert StrategyNotAllocated();
        if (rec.defundedAt != 0) revert AllocationDefunded();

        // Pull realized PnL from the strategy (allocator-vault-wide), then keep
        // the user's prorated share. Strategy fee is taken from the user's PnL
        // share above the per-allocation high-water mark.
        uint256 balBefore = baseAsset.balanceOf(address(this));
        IStrategyVault(strategy).distributeRealized(address(this));
        uint256 realizedTotal = baseAsset.balanceOf(address(this)) - balBefore;
        if (realizedTotal == 0) {
            emit StrategyFeeSettled(user, strategy, 0, rec.strategyHighWaterMark);
            return;
        }

        uint256 deployed = rec.capitalDeployed;
        uint256 totalAlloc = IStrategyVault(strategy).allocationOf(address(this));
        // After distributeRealized, the strategy has reduced totalNAV by exactly
        // realizedTotal. Apportion to user by their share of allocator deployed.
        uint256 userRealized =
            totalAlloc == 0 ? realizedTotal : (realizedTotal * deployed) / totalAlloc;

        uint16 stratFeeBps = IStrategyVault(strategy).manifest().feeRateBps;
        uint256 stratFee = (userRealized * stratFeeBps) / 10_000;
        uint256 allocFee = (userRealized * allocatorFeeRateBps) / 10_000;
        uint256 toUser = userRealized - stratFee - allocFee;

        // Strategy fee → strategy operator.
        if (stratFee > 0) {
            address stratOp = IStrategyVault(strategy).manifest().operator;
            baseAsset.safeTransfer(stratOp, stratFee);
        }
        // Allocator fee → vault accrual.
        _accruedFees += allocFee;

        // Net user PnL → user vault.
        if (toUser > 0) {
            baseAsset.forceApprove(userVault, toUser);
            IUserVaultForAllocator(userVault).creditFromAllocator(user, toUser);
        }

        // Bump high-water mark.
        rec.strategyHighWaterMark += userRealized;

        // Forward any unattributed dust (rounding) to allocator fees.
        uint256 leftover = realizedTotal - userRealized;
        if (leftover > 0) _accruedFees += leftover;

        emit StrategyFeeSettled(user, strategy, stratFee, rec.strategyHighWaterMark);
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

        // Pull principal.
        uint256 principal = rec.capitalDeployed;
        if (principal > 0) {
            IStrategyVault(strategy).withdrawToAllocator(address(this), principal);
            _userTotalDeployed[user] -= principal;
        }
        if (rec.strategy != address(0)) _userActiveStrategyCount[user] -= 1;

        rec.capitalDeployed = 0;

        // Credit user's full balance back (principal + their share of realized).
        uint256 totalBack = principal + realized;
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

        // Class-allowed check
        bytes32 declared = IStrategyVault(strategy).manifest().declaredClass;
        bool classOK;
        for (uint256 i = 0; i < meta.allowedStrategyClasses.length; i++) {
            if (meta.allowedStrategyClasses[i] == declared) {
                classOK = true;
                break;
            }
        }
        if (!classOK) revert MetaClassNotAllowed();
    }

    function _maxU256(uint256 a, uint256 b) internal pure returns (uint256) {
        return a > b ? a : b;
    }
}
