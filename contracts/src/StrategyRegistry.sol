// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Ownable } from "@openzeppelin/contracts/access/Ownable.sol";
import { ReentrancyGuard } from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import { IERC20 } from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import { SafeERC20 } from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

import { IStrategyRegistry } from "./interfaces/IStrategyRegistry.sol";

/// @title StrategyRegistry
/// @notice Canonical strategy directory on Kite. Holds stake, anchors reputation,
///         enforces a 7-day cooldown on stake withdrawals to prevent rug-after-allocation.
///         Helios.md §6.5.
contract StrategyRegistry is IStrategyRegistry, Ownable, ReentrancyGuard {
    using SafeERC20 for IERC20;

    IERC20 public immutable stakeToken;
    address public immutable reputationAnchor;
    uint256 public immutable stakeCooldown;

    struct PendingWithdrawal {
        uint256 amount;
        uint64 unlockAt;
    }

    mapping(address => StrategyEntry) internal _strategies;
    mapping(address => PendingWithdrawal) public pendingWithdrawals;
    mapping(bytes32 => address[]) internal _strategiesByClass;
    address[] public strategyList;

    error StrategyAlreadyRegistered();
    error StrategyNotFound();
    error WithdrawalExceedsStake();
    error WithdrawalAlreadyPending();
    error NoPendingWithdrawal();
    error ZeroAmount();
    error ZeroAddress();
    error StrategyInactive();
    error SlashExceedsStake();

    constructor(
        IERC20 stakeToken_,
        address reputationAnchor_,
        address owner_,
        uint256 stakeCooldown_
    ) Ownable(owner_) {
        if (
            address(stakeToken_) == address(0) || reputationAnchor_ == address(0)
                || owner_ == address(0)
        ) {
            revert ZeroAddress();
        }
        stakeToken = stakeToken_;
        reputationAnchor = reputationAnchor_;
        stakeCooldown = stakeCooldown_;
    }

    // ── Registration ────────────────────────────────────────────────

    function registerStrategy(address vault, bytes32 declaredClass, uint256 stakeAmount)
        external
        nonReentrant
        returns (address strategyId)
    {
        if (vault == address(0)) revert ZeroAddress();
        if (stakeAmount == 0) revert ZeroAmount();
        if (_strategies[vault].registeredAt != 0) revert StrategyAlreadyRegistered();

        stakeToken.safeTransferFrom(msg.sender, address(this), stakeAmount);

        _strategies[vault] = StrategyEntry({
            vault: vault,
            operator: msg.sender,
            declaredClass: declaredClass,
            stakeAmount: stakeAmount,
            currentReputation: 0,
            registeredAt: uint64(block.timestamp),
            active: true
        });
        strategyList.push(vault);
        _strategiesByClass[declaredClass].push(vault);

        emit StrategyRegistered(vault, vault, msg.sender, declaredClass, stakeAmount);
        return vault;
    }

    // ── Stake management ────────────────────────────────────────────

    function topUpStake(address strategyId, uint256 amount) external nonReentrant {
        if (amount == 0) revert ZeroAmount();
        StrategyEntry storage s = _strategies[strategyId];
        if (s.registeredAt == 0) revert StrategyNotFound();

        stakeToken.safeTransferFrom(msg.sender, address(this), amount);
        s.stakeAmount += amount;

        emit StakeToppedUp(strategyId, amount);
    }

    function initiateStakeWithdrawal(address strategyId, uint256 amount) external {
        if (amount == 0) revert ZeroAmount();
        StrategyEntry storage s = _strategies[strategyId];
        if (s.registeredAt == 0) revert StrategyNotFound();
        if (msg.sender != s.operator) revert NotOperator();
        if (amount > s.stakeAmount) revert WithdrawalExceedsStake();
        if (pendingWithdrawals[strategyId].amount != 0) revert WithdrawalAlreadyPending();

        uint64 unlockAt = uint64(block.timestamp + stakeCooldown);
        pendingWithdrawals[strategyId] = PendingWithdrawal({ amount: amount, unlockAt: unlockAt });

        emit StakeWithdrawalInitiated(strategyId, amount, unlockAt);
    }

    function completeStakeWithdrawal(address strategyId) external nonReentrant {
        StrategyEntry storage s = _strategies[strategyId];
        if (s.registeredAt == 0) revert StrategyNotFound();
        if (msg.sender != s.operator) revert NotOperator();

        PendingWithdrawal memory p = pendingWithdrawals[strategyId];
        if (p.amount == 0) revert NoPendingWithdrawal();
        if (block.timestamp < p.unlockAt) revert StakeCooldownActive();
        if (p.amount > s.stakeAmount) revert WithdrawalExceedsStake();

        s.stakeAmount -= p.amount;
        delete pendingWithdrawals[strategyId];
        stakeToken.safeTransfer(s.operator, p.amount);

        emit StakeWithdrawn(strategyId, p.amount);
    }

    function deactivate(address strategyId) external {
        StrategyEntry storage s = _strategies[strategyId];
        if (s.registeredAt == 0) revert StrategyNotFound();
        if (msg.sender != s.operator) revert NotOperator();
        if (!s.active) revert StrategyInactive();

        s.active = false;
        emit StrategyDeactivated(strategyId);
    }

    // ── Reputation + slashing ───────────────────────────────────────

    function updateReputation(address strategyId, int256 delta) external {
        if (msg.sender != reputationAnchor) revert NotReputationAnchor();
        StrategyEntry storage s = _strategies[strategyId];
        if (s.registeredAt == 0) revert StrategyNotFound();

        int256 newScore = s.currentReputation + delta;
        s.currentReputation = newScore;

        emit ReputationUpdated(strategyId, delta, newScore);
    }

    function slash(address strategyId, uint256 amount, string calldata reason) external onlyOwner {
        StrategyEntry storage s = _strategies[strategyId];
        if (s.registeredAt == 0) revert StrategyNotFound();
        if (amount == 0) revert ZeroAmount();
        if (amount > s.stakeAmount) revert SlashExceedsStake();

        s.stakeAmount -= amount;
        stakeToken.safeTransfer(owner(), amount);

        emit StrategySlashed(strategyId, amount, reason);
    }

    // ── Views ───────────────────────────────────────────────────────

    function strategyOf(address strategyId) external view returns (StrategyEntry memory) {
        return _strategies[strategyId];
    }

    function strategiesByClass(bytes32 declaredClass) external view returns (address[] memory) {
        return _strategiesByClass[declaredClass];
    }

    function strategyCount() external view returns (uint256) {
        return strategyList.length;
    }
}
