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

    error NotAllocator();
    error AllocationOutOfBounds();
    error DrawdownNotBreached();

    function allocateToStrategy(address user, address strategy, uint256 amount) external;
    function defundStrategy(address user, address strategy, string calldata reason) external;
    function rebalance(address user, address[] calldata strategies, uint256[] calldata weightsBps)
        external;
    function settleStrategyFee(address user, address strategy) external;
    function withdrawAllocatorFees() external;

    function allocationOf(address user, address strategy)
        external
        view
        returns (AllocationRecord memory);
    function accruedFees() external view returns (uint256);
}
