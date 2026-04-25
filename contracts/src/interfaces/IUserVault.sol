// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {MetaStrategyLib} from "./IMetaStrategy.sol";

/// @notice UserVault — per-user custody + meta-strategy enforcement + allocator delegation.
///         Helios.md §6.2.
interface IUserVault {
    event MetaStrategySet(address indexed user, bytes32 indexed metaStrategyHash);
    event Deposited(address indexed user, address indexed asset, uint256 amount);
    event AllocatorDelegated(
        address indexed user,
        address indexed allocator,
        uint64 sessionTTL,
        bytes32 sessionKey
    );
    event AllocatorFeeSettled(
        address indexed user,
        address indexed allocator,
        uint256 feeAmount,
        uint256 newHighWaterMark
    );
    event Withdrawn(address indexed user, address indexed asset, uint256 amount);

    error OutOfBoundsDelegation();
    error MetaStrategyExpired();
    error InvalidSignature();

    function setMetaStrategy(
        MetaStrategyLib.MetaStrategy calldata meta,
        bytes calldata signature
    ) external;

    function deposit(address asset, uint256 amount) external;

    function delegateToAllocator(address allocator, uint64 sessionTTL) external;

    function withdraw(address asset, uint256 amount) external;

    function settleAllocatorFee(address allocator) external;

    function metaStrategyOf(address user) external view returns (MetaStrategyLib.MetaStrategy memory);
    function allocatorOf(address user) external view returns (address);
    function highWaterMarkOf(address user) external view returns (uint256);
}
