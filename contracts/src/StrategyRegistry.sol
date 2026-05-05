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

    struct PendingParamsRotation {
        bytes32 newHash;
        uint64 unlockAt;
    }

    mapping(address => StrategyEntry) internal _strategies;
    mapping(address => PendingWithdrawal) public pendingWithdrawals;
    mapping(bytes32 => address[]) internal _strategiesByClass;
    address[] public strategyList;

    // WS3.A — per-class market allowlist root (yield_rotation_v1 et al.).
    // Helios.md §6.5 / §9.3.
    mapping(bytes32 => bytes32) internal _marketAllowlistRoot;

    // WS7.A — committed params hash per strategy. Initial commit lives
    // here so the StrategyVault can require pre-trade equality without
    // operator-time tampering. Rotations follow the same cooldown shape
    // as stake withdrawals.
    mapping(address => bytes32) internal _paramsHashOf;
    mapping(address => PendingParamsRotation) internal _pendingParamsRotation;

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

        // phase2-review.md: cancel any pending params rotation alongside the
        // deactivation so a subsequent `completeParamsRotation` can't mutate
        // the active hash on a strategy whose vault is no longer accepting
        // capital. Without this, op could `initiateParamsRotation` →
        // `deactivate` → wait cooldown → `completeParamsRotation` and ship a
        // new params hash that the rest of the system thinks is dead.
        bytes32 pendingHash = _pendingParamsRotation[strategyId].newHash;
        if (pendingHash != bytes32(0)) {
            delete _pendingParamsRotation[strategyId];
            emit ParamsRotationCancelled(strategyId, pendingHash);
        }

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
        if (s.stakeAmount == 0) s.active = false;
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

    // ── WS3.A: per-class market allowlist ───────────────────────────

    function setMarketAllowlistRoot(bytes32 declaredClass, bytes32 root) external onlyOwner {
        _marketAllowlistRoot[declaredClass] = root;
        emit MarketAllowlistRootSet(declaredClass, root);
    }

    function marketAllowlistRoot(bytes32 declaredClass) external view returns (bytes32) {
        return _marketAllowlistRoot[declaredClass];
    }

    // ── WS7.A: params-hash commitment + rotation ────────────────────

    /// @notice One-shot initial commit of a strategy's params hash. Must
    ///         be called by the operator after `registerStrategy` and
    ///         before the vault attempts its first trade. After this
    ///         point, mutations require `initiateParamsRotation` +
    ///         `completeParamsRotation` (cooldown enforced).
    function commitInitialParamsHash(address strategyId, bytes32 paramsHash) external {
        StrategyEntry storage s = _strategies[strategyId];
        if (s.registeredAt == 0) revert StrategyNotFound();
        if (msg.sender != s.operator) revert NotOperator();
        if (_paramsHashOf[strategyId] != bytes32(0)) revert ParamsHashAlreadyCommitted();
        // StrategyVault keys "uncommitted" off the registry returning zero
        // (`_activeParamsHash` reverts with `ParamsHashNotCommitted`). Allowing
        // a zero commit would re-open the bypass it closes.
        if (paramsHash == bytes32(0)) revert ZeroParamsHash();

        _paramsHashOf[strategyId] = paramsHash;
        emit ParamsHashCommitted(strategyId, paramsHash);
    }

    function initiateParamsRotation(address strategyId, bytes32 newParamsHash) external {
        StrategyEntry storage s = _strategies[strategyId];
        if (s.registeredAt == 0) revert StrategyNotFound();
        if (msg.sender != s.operator) revert NotOperator();
        if (_paramsHashOf[strategyId] == bytes32(0)) revert ParamsHashNotCommitted();
        if (_pendingParamsRotation[strategyId].newHash != bytes32(0)) {
            revert ParamsRotationAlreadyPending();
        }

        uint64 unlockAt = uint64(block.timestamp + stakeCooldown);
        _pendingParamsRotation[strategyId] =
            PendingParamsRotation({ newHash: newParamsHash, unlockAt: unlockAt });

        emit ParamsRotationInitiated(strategyId, _paramsHashOf[strategyId], newParamsHash, unlockAt);
    }

    function completeParamsRotation(address strategyId) external {
        StrategyEntry storage s = _strategies[strategyId];
        if (s.registeredAt == 0) revert StrategyNotFound();
        if (msg.sender != s.operator) revert NotOperator();

        PendingParamsRotation memory p = _pendingParamsRotation[strategyId];
        if (p.newHash == bytes32(0)) revert NoPendingParamsRotation();
        if (block.timestamp < p.unlockAt) revert ParamsRotationCooldownActive();

        bytes32 oldHash = _paramsHashOf[strategyId];
        _paramsHashOf[strategyId] = p.newHash;
        delete _pendingParamsRotation[strategyId];

        emit ParamsRotated(strategyId, oldHash, p.newHash);
    }

    function paramsHashOf(address strategyId) external view returns (bytes32) {
        return _paramsHashOf[strategyId];
    }

    function pendingParamsHashOf(address strategyId)
        external
        view
        returns (bytes32 newHash, uint64 unlockAt)
    {
        PendingParamsRotation memory p = _pendingParamsRotation[strategyId];
        return (p.newHash, p.unlockAt);
    }
}
