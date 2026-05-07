// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Ownable } from "@openzeppelin/contracts/access/Ownable.sol";
import { ReentrancyGuard } from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import { IERC20 } from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import { SafeERC20 } from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

import { IAllocatorRegistry } from "./interfaces/IAllocatorRegistry.sol";

/// @title AllocatorRegistry
/// @notice Allocator directory on Kite. Same stake/cooldown/slash shape as
///         StrategyRegistry, plus a reserved-name policy that locks "Helios
///         Sentinel" / "Helios Helix" to multi-sig-approved deployers.
///         Helios.md §6.6.
contract AllocatorRegistry is IAllocatorRegistry, Ownable, ReentrancyGuard {
    using SafeERC20 for IERC20;

    IERC20 public immutable stakeToken;
    address public immutable reputationAnchor;
    uint256 public immutable stakeCooldown;

    struct PendingWithdrawal {
        uint256 amount;
        uint64 unlockAt;
    }

    mapping(address => AllocatorEntry) internal _allocators;
    mapping(address => PendingWithdrawal) public pendingWithdrawals;
    mapping(bytes32 => bool) internal _reservedNames; // keccak256(lower(name)) => reserved
    mapping(bytes32 => address) internal _nameToAllocator;
    address[] public allocatorList;

    error AllocatorAlreadyRegistered();
    error AllocatorNotFound();
    error WithdrawalExceedsStake();
    error WithdrawalAlreadyPending();
    error NoPendingWithdrawal();
    error ZeroAmount();
    error ZeroAddress();
    error AllocatorInactive();
    error SlashExceedsStake();
    error EmptyName();
    error NameAlreadyTaken();
    error NameNotReserved();
    error StakeCooldownActive();

    constructor(
        IERC20 stakeToken_,
        address reputationAnchor_,
        address owner_,
        uint256 stakeCooldown_
    ) Ownable(owner_) {
        if (address(stakeToken_) == address(0) || reputationAnchor_ == address(0)) {
            revert ZeroAddress();
        }
        stakeToken = stakeToken_;
        reputationAnchor = reputationAnchor_;
        stakeCooldown = stakeCooldown_;

        // Pre-seed the two Helios reference brands so they can't be squatted
        // before the owner gets around to calling reserveName.
        _reserve("helios sentinel");
        _reserve("helios helix");
    }

    // ── Registration ────────────────────────────────────────────────

    function registerAllocator(
        string calldata name,
        address operatorVault,
        bytes32 rankingFunctionHash,
        bytes32[] calldata supportedClasses,
        uint16 feeRateBps,
        uint256 stakeAmount
    ) external nonReentrant returns (address allocatorId) {
        if (operatorVault == address(0)) revert ZeroAddress();
        if (stakeAmount == 0) revert ZeroAmount();
        if (bytes(name).length == 0) revert EmptyName();
        if (_allocators[operatorVault].registeredAt != 0) revert AllocatorAlreadyRegistered();

        bytes32 nameKey = _nameKey(name);
        if (_reservedNames[nameKey]) revert ReservedName();
        if (_nameToAllocator[nameKey] != address(0)) revert NameAlreadyTaken();

        stakeToken.safeTransferFrom(msg.sender, address(this), stakeAmount);

        _allocators[operatorVault] = AllocatorEntry({
            name: name,
            operatorVault: operatorVault,
            operator: msg.sender,
            rankingFunctionHash: rankingFunctionHash,
            supportedClasses: supportedClasses,
            feeRateBps: feeRateBps,
            stakeAmount: stakeAmount,
            currentReputation: 0,
            totalUsers: 0,
            totalCapitalManaged: 0,
            registeredAt: uint64(block.timestamp),
            active: true,
            isReferenceBrand: false
        });
        allocatorList.push(operatorVault);
        _nameToAllocator[nameKey] = operatorVault;

        emit AllocatorRegistered(
            operatorVault,
            name,
            operatorVault,
            msg.sender,
            rankingFunctionHash,
            feeRateBps,
            stakeAmount
        );
        return operatorVault;
    }

    // ── Stake management ────────────────────────────────────────────

    function topUpStake(address allocatorId, uint256 amount) external nonReentrant {
        if (amount == 0) revert ZeroAmount();
        AllocatorEntry storage a = _allocators[allocatorId];
        if (a.registeredAt == 0) revert AllocatorNotFound();

        stakeToken.safeTransferFrom(msg.sender, address(this), amount);
        a.stakeAmount += amount;

        emit AllocatorStakeToppedUp(allocatorId, amount);
    }

    function initiateStakeWithdrawal(address allocatorId, uint256 amount) external {
        if (amount == 0) revert ZeroAmount();
        AllocatorEntry storage a = _allocators[allocatorId];
        if (a.registeredAt == 0) revert AllocatorNotFound();
        if (msg.sender != a.operator) revert NotAllocatorOperator();
        if (amount > a.stakeAmount) revert WithdrawalExceedsStake();
        if (pendingWithdrawals[allocatorId].amount != 0) revert WithdrawalAlreadyPending();

        uint64 unlockAt = uint64(block.timestamp + stakeCooldown);
        pendingWithdrawals[allocatorId] = PendingWithdrawal({ amount: amount, unlockAt: unlockAt });

        emit AllocatorStakeWithdrawalInitiated(allocatorId, amount, unlockAt);
    }

    function completeStakeWithdrawal(address allocatorId) external nonReentrant {
        AllocatorEntry storage a = _allocators[allocatorId];
        if (a.registeredAt == 0) revert AllocatorNotFound();
        if (msg.sender != a.operator) revert NotAllocatorOperator();

        PendingWithdrawal memory p = pendingWithdrawals[allocatorId];
        if (p.amount == 0) revert NoPendingWithdrawal();
        if (block.timestamp < p.unlockAt) revert StakeCooldownActive();
        if (p.amount > a.stakeAmount) revert WithdrawalExceedsStake();

        a.stakeAmount -= p.amount;
        delete pendingWithdrawals[allocatorId];
        stakeToken.safeTransfer(a.operator, p.amount);

        emit AllocatorStakeWithdrawn(allocatorId, p.amount);
    }

    function deactivate(address allocatorId) external {
        AllocatorEntry storage a = _allocators[allocatorId];
        if (a.registeredAt == 0) revert AllocatorNotFound();
        if (msg.sender != a.operator) revert NotAllocatorOperator();
        if (!a.active) revert AllocatorInactive();

        a.active = false;
        emit AllocatorDeactivated(allocatorId);
    }

    // ── Reputation + slashing ───────────────────────────────────────

    function updateReputation(address allocatorId, int256 delta) external {
        if (msg.sender != reputationAnchor) revert NotReputationAnchor();
        AllocatorEntry storage a = _allocators[allocatorId];
        if (a.registeredAt == 0) revert AllocatorNotFound();

        int256 newScore = a.currentReputation + delta;
        a.currentReputation = newScore;

        emit AllocatorReputationUpdated(allocatorId, delta, newScore);
    }

    function slash(address allocatorId, uint256 amount, string calldata reason) external onlyOwner {
        AllocatorEntry storage a = _allocators[allocatorId];
        if (a.registeredAt == 0) revert AllocatorNotFound();
        if (amount == 0) revert ZeroAmount();
        if (amount > a.stakeAmount) revert SlashExceedsStake();

        a.stakeAmount -= amount;
        if (a.stakeAmount == 0) a.active = false;
        stakeToken.safeTransfer(owner(), amount);

        emit AllocatorSlashed(allocatorId, amount, reason);
    }

    // ── Reserved-name administration ────────────────────────────────

    function reserveName(string calldata name) external onlyOwner {
        if (bytes(name).length == 0) revert EmptyName();
        // Reserving a name that's currently held by an existing allocator is
        // allowed: the existing allocator keeps the name; reservation locks
        // the name from being claimed by a *new* registration after the
        // existing allocator deregisters or deactivates. This is what makes
        // assignReferenceBrand workable post-hoc on a multi-sig-deployed allocator.
        _reserve(name);
    }

    function assignReferenceBrand(address allocatorId) external onlyOwner {
        AllocatorEntry storage a = _allocators[allocatorId];
        if (a.registeredAt == 0) revert AllocatorNotFound();
        bytes32 key = _nameKey(a.name);
        // Reference brands must occupy a reserved name. If the name was
        // reserved AFTER registration the registry still considers it taken
        // by this allocator, so the reserved flag is the gating signal.
        if (!_reservedNames[key]) revert NameNotReserved();
        a.isReferenceBrand = true;
        emit ReferenceBrandAssigned(allocatorId);
    }

    // ── Views ───────────────────────────────────────────────────────

    function allocatorOf(address allocatorId) external view returns (AllocatorEntry memory) {
        return _allocators[allocatorId];
    }

    function allocatorByName(string calldata name) external view returns (address) {
        return _nameToAllocator[_nameKey(name)];
    }

    function isNameReserved(string calldata name) external view returns (bool) {
        return _reservedNames[_nameKey(name)];
    }

    function allocatorCount() external view returns (uint256) {
        return allocatorList.length;
    }

    // ── Internal ────────────────────────────────────────────────────

    function _reserve(string memory name) internal {
        bytes32 key = _nameKey(name);
        _reservedNames[key] = true;
        emit NameReserved(name);
    }

    /// @dev Normalize the name before hashing so visually-identical
    ///      handles collide. Steps:
    ///        1. Strip ASCII whitespace (space, tab, CR, LF) and the most
    ///           common zero-width Unicode bytes (U+200B…U+200D, U+FEFF
    ///           encoded as their UTF-8 byte sequences) anywhere in the
    ///           string. Phase-3 review MEDIUM in
    ///           `docs/phase-3-review.md`: trailing space and zero-width
    ///           tricks were brand-impersonation vectors.
    ///        2. ASCII-lower-case A-Z. Non-ASCII Unicode case folding is
    ///           still a documented v1 weakness — full ICU normalization
    ///           is a Phase 4+ item.
    function _nameKey(string memory name) internal pure returns (bytes32) {
        bytes memory b = bytes(name);
        bytes memory out = new bytes(b.length);
        uint256 j;
        for (uint256 i = 0; i < b.length; i++) {
            uint8 c = uint8(b[i]);
            // ASCII whitespace.
            if (c == 0x20 || c == 0x09 || c == 0x0A || c == 0x0D) continue;
            // Zero-width and BOM, encoded as UTF-8: U+200B 0xE2 0x80 0x8B,
            // U+200C 0xE2 0x80 0x8C, U+200D 0xE2 0x80 0x8D,
            // U+FEFF 0xEF 0xBB 0xBF. Detect the 3-byte prefix and skip the
            // run.
            if (c == 0xE2 && i + 2 < b.length && uint8(b[i + 1]) == 0x80) {
                uint8 third = uint8(b[i + 2]);
                if (third == 0x8B || third == 0x8C || third == 0x8D) {
                    i += 2;
                    continue;
                }
            }
            if (c == 0xEF && i + 2 < b.length && uint8(b[i + 1]) == 0xBB && uint8(b[i + 2]) == 0xBF)
            {
                i += 2;
                continue;
            }
            // ASCII upper -> lower.
            if (c >= 0x41 && c <= 0x5A) {
                out[j++] = bytes1(c + 32);
            } else {
                out[j++] = b[i];
            }
        }
        // Truncate to actual written length before hashing.
        bytes memory packed = new bytes(j);
        for (uint256 k = 0; k < j; k++) {
            packed[k] = out[k];
        }
        return keccak256(packed);
    }
}
