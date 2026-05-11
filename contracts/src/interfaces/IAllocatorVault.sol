// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

/// @notice AllocatorVault — per-allocator working capital + per-strategy allocations.
///         Helios.md §6.3.
interface IAllocatorVault {
    struct AllocationRecord {
        address strategy;
        uint256 capitalDeployed;
        uint256 strategyHighWaterMark;
        uint64 lastRebalanceTimestamp;
        uint64 defundedAt; // 0 if active
    }

    /// @notice Per-(user,strategy) state for the Phase-4 caller-cadence
    ///         permissionless defund path (Helios.md §6.3). The first
    ///         `triggerDefund` call posts the bond and records this
    ///         entry; subsequent calls advance `breachCount` once
    ///         spaced ≥ `MIN_BAR_BLOCKS` apart, or clear the entry
    ///         (refunding the bond) if NAV recovered.
    /// @dev    Packs into two storage slots: 64+64+64+8+address(160)
    ///         = 360 bits + uint128 bond on slot two.
    struct PendingDefund {
        uint64 firstObservedAt; // block.timestamp at first observation
        uint64 firstObservedBlock; // block.number at first observation
        uint64 lastObservedBlock; // block.number at most-recent observation
        uint8 breachCount; // consecutive breach observations
        address triggerer; // bond poster
        uint128 bondAmount; // USDC e6
    }

    event AllocationCreated(
        address indexed user, address indexed strategy, uint256 amount, uint32 chainId
    );
    event AllocationIncreased(address indexed user, address indexed strategy, uint256 delta);
    event AllocationDecreased(address indexed user, address indexed strategy, uint256 delta);
    event StrategyDefunded(
        address indexed user, address indexed strategy, string reason, address indexed triggeredBy
    );
    event StrategyFeeSettled(
        address indexed user, address indexed strategy, uint256 feeAmount, uint256 newHighWaterMark
    );
    event AllocatorFeesWithdrawn(address indexed allocator, uint256 amount);

    /// @notice One observation of the permissionless defund trigger.
    /// @param breachCount         Counter after this observation.
    /// @param observedDrawdownBps Drawdown vs HWM at the read site (bps).
    /// @param bondAmount          Bond posted by `triggerer` on the first
    ///                            observation; 0 on subsequent observations.
    event DefundObserved(
        address indexed user,
        address indexed strategy,
        address indexed triggerer,
        uint8 breachCount,
        uint256 observedDrawdownBps,
        uint256 bondAmount
    );
    /// @notice Emitted once `breachCount == defundTwapBars`. The pending
    ///         entry is now eligible to call `finalizeDefund` after
    ///         `defundConfirmBlocks` elapse since `armedAtBlock`.
    event DefundArmed(address indexed user, address indexed strategy, uint64 armedAtBlock);
    /// @notice Pending entry cleared without finalizing. `reason` ∈
    ///         `keccak256("RECOVERED")` (NAV recovered above threshold)
    ///         or `keccak256("OPERATOR_CANCEL")` (operator override).
    event DefundCancelled(address indexed user, address indexed strategy, bytes32 reason);
    /// @notice Permissionless defund finalize outcome.
    /// @param refunded      Bond returned to `triggerer` (full bond, or 0 on slash-to-user).
    /// @param reward        Reward paid from strategy stake (0 on slash-to-user; capped).
    /// @param slashedToUser Bond slashed to the user's `UserVault` if NAV recovered (0 on success).
    event DefundFinalized(
        address indexed user,
        address indexed strategy,
        address triggerer,
        uint256 refunded,
        uint256 reward,
        uint256 slashedToUser
    );
    /// @notice Owner-only oracle anchor wiring. Empty (0x0) disables
    ///         the freshness gate — must be set before `triggerDefund`
    ///         is callable in production.
    event OracleAnchorUpdated(address indexed previous, address indexed next);
    /// @notice Owner-only reward cap rotation, in USDC e6 units.
    event DefundRewardCapUpdated(uint256 previous, uint256 next);
    /// @notice Owner-only `strategyRegistry` pointer rotation. Used by
    ///         the WS11 V1→V2 ReputationAnchor cutover (Phase-6) to
    ///         swap the immutable-registry pointer the vault was
    ///         initialised against.
    event StrategyRegistryUpdated(address indexed previous, address indexed next);

    error NotAllocator();
    error AllocationOutOfBounds();
    error DrawdownNotBreached();
    /// @notice `block.timestamp - OraclePriceAnchor.latest().committedAt
    ///         > MAX_STALENESS_SEC`, or no commits yet. Only checked on
    ///         the first observation of a pending entry.
    error OracleStale();
    /// @notice `oracleAnchor` not configured. Set via `setOracleAnchor`
    ///         after deploy/upgrade.
    error OracleAnchorNotSet();
    /// @notice Subsequent observation came in less than `MIN_BAR_BLOCKS`
    ///         after the previous one. The caller wasted gas; no state
    ///         change.
    error BarTooSoon();
    /// @notice `finalizeDefund` called before `breachCount` reached
    ///         `defundTwapBars`.
    error DefundNotArmed();
    /// @notice `cancelDefund` / `finalizeDefund` called with no pending
    ///         entry.
    error DefundNotPending();
    /// @notice `finalizeDefund` called before `lastObservedBlock +
    ///         defundConfirmBlocks` elapsed.
    error ConfirmWindowNotElapsed();

    function allocateToStrategy(address user, address strategy, uint256 amount) external;
    function defundStrategy(address user, address strategy, string calldata reason) external;
    function rebalance(address user, address[] calldata strategies, uint256[] calldata weightsBps)
        external;
    function settleStrategyFee(address user, address strategy) external;
    function withdrawAllocatorFees() external;

    /// @notice Permissionless defund — first observation. Posts bond.
    function triggerDefund(address user, address strategy) external;
    /// @notice Permissionless defund — finalize once armed and the
    ///         confirm window has elapsed.
    function finalizeDefund(address user, address strategy) external;
    /// @notice Operator override that clears a pending entry and
    ///         refunds the bond to `triggerer`.
    function cancelDefund(address user, address strategy) external;

    function allocationOf(address user, address strategy)
        external
        view
        returns (AllocationRecord memory);
    function pendingDefundOf(address user, address strategy)
        external
        view
        returns (PendingDefund memory);
    function accruedFees() external view returns (uint256);
}
