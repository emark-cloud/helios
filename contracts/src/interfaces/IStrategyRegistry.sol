// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

/// @notice Strategy directory on Kite. Helios.md §6.5.
interface IStrategyRegistry {
    struct StrategyEntry {
        address vault;
        address operator;
        bytes32 declaredClass;
        uint256 stakeAmount;
        int256 currentReputation;
        uint64 registeredAt;
        bool active;
    }

    event StrategyRegistered(
        address indexed strategyId,
        address indexed vault,
        address indexed operator,
        bytes32 declaredClass,
        uint256 stakeAmount
    );
    event StakeToppedUp(address indexed strategyId, uint256 amount);
    event StakeWithdrawalInitiated(address indexed strategyId, uint256 amount, uint64 unlockAt);
    event StakeWithdrawn(address indexed strategyId, uint256 amount);
    event StrategyDeactivated(address indexed strategyId);
    event ReputationUpdated(address indexed strategyId, int256 delta, int256 newScore);
    event StrategySlashed(address indexed strategyId, uint256 amount, string reason);
    event MarketAllowlistRootSet(bytes32 indexed declaredClass, bytes32 root);
    event ParamsHashCommitted(address indexed strategyId, bytes32 paramsHash);
    event ParamsRotationInitiated(
        address indexed strategyId, bytes32 oldHash, bytes32 newHash, uint64 unlockAt
    );
    event ParamsRotated(address indexed strategyId, bytes32 oldHash, bytes32 newHash);

    error StakeCooldownActive();
    error NotReputationAnchor();
    error NotOperator();
    error ParamsRotationCooldownActive();
    error NoPendingParamsRotation();
    error ParamsRotationAlreadyPending();
    error ParamsHashAlreadyCommitted();
    error ParamsHashNotCommitted();

    function registerStrategy(address vault, bytes32 declaredClass, uint256 stakeAmount)
        external
        returns (address strategyId);

    function topUpStake(address strategyId, uint256 amount) external;
    function initiateStakeWithdrawal(address strategyId, uint256 amount) external;
    function completeStakeWithdrawal(address strategyId) external;
    function deactivate(address strategyId) external;
    function updateReputation(address strategyId, int256 delta) external;
    function slash(address strategyId, uint256 amount, string calldata reason) external;

    function strategyOf(address strategyId) external view returns (StrategyEntry memory);
    function strategiesByClass(bytes32 declaredClass) external view returns (address[] memory);

    // ── WS3.A: per-class market allowlist (yield_rotation_v1) ───────
    function setMarketAllowlistRoot(bytes32 declaredClass, bytes32 root) external;
    function marketAllowlistRoot(bytes32 declaredClass) external view returns (bytes32);

    // ── WS7.A: params-hash commitment + rotation ────────────────────
    function commitInitialParamsHash(address strategyId, bytes32 paramsHash) external;
    function initiateParamsRotation(address strategyId, bytes32 newParamsHash) external;
    function completeParamsRotation(address strategyId) external;
    function paramsHashOf(address strategyId) external view returns (bytes32);
    function pendingParamsHashOf(address strategyId)
        external
        view
        returns (bytes32 newHash, uint64 unlockAt);
}
