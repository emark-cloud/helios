// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

/// @notice Allocator directory on Kite. Mirrors StrategyRegistry but tracks allocators.
///         Enforces the reserved-name policy for "Helios Sentinel" / "Helios Helix".
///         Helios.md §6.6.
interface IAllocatorRegistry {
    struct AllocatorEntry {
        string name;
        address operatorVault;
        address operator;
        bytes32 rankingFunctionHash;
        bytes32[] supportedClasses;
        uint16 feeRateBps;
        uint256 stakeAmount;
        int256 currentReputation;
        uint256 totalUsers;
        uint256 totalCapitalManaged;
        uint64 registeredAt;
        bool active;
        bool isReferenceBrand;
    }

    event AllocatorRegistered(
        address indexed allocatorId,
        string name,
        address indexed operatorVault,
        address indexed operator,
        bytes32 rankingFunctionHash,
        uint16 feeRateBps,
        uint256 stakeAmount
    );
    event AllocatorStakeToppedUp(address indexed allocatorId, uint256 amount);
    event AllocatorStakeWithdrawalInitiated(
        address indexed allocatorId, uint256 amount, uint64 unlockAt
    );
    event AllocatorStakeWithdrawn(address indexed allocatorId, uint256 amount);
    event AllocatorDeactivated(address indexed allocatorId);
    event AllocatorReputationUpdated(address indexed allocatorId, int256 delta, int256 newScore);
    event AllocatorSlashed(address indexed allocatorId, uint256 amount, string reason);
    event NameReserved(string name);
    event ReferenceBrandAssigned(address indexed allocatorId);

    error ReservedName();
    error NotAllocatorOperator();
    error NotReputationAnchor();

    function registerAllocator(
        string calldata name,
        address operatorVault,
        bytes32 rankingFunctionHash,
        bytes32[] calldata supportedClasses,
        uint16 feeRateBps,
        uint256 stakeAmount
    ) external returns (address allocatorId);

    function topUpStake(address allocatorId, uint256 amount) external;
    function initiateStakeWithdrawal(address allocatorId, uint256 amount) external;
    function completeStakeWithdrawal(address allocatorId) external;
    function deactivate(address allocatorId) external;
    function updateReputation(address allocatorId, int256 delta) external;
    function slash(address allocatorId, uint256 amount, string calldata reason) external;

    // Reserved-name admin — Helios multi-sig only.
    function reserveName(string calldata name) external;
    function assignReferenceBrand(address allocatorId) external;

    function allocatorOf(address allocatorId) external view returns (AllocatorEntry memory);
    function allocatorByName(string calldata name) external view returns (address);
    function isNameReserved(string calldata name) external view returns (bool);
}
