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

import { IUserVault } from "./interfaces/IUserVault.sol";
import { MetaStrategyLib } from "./interfaces/IMetaStrategy.sol";

/// @title UserVault
/// @notice Per-user custody + meta-strategy enforcement + allocator delegation.
///         Phase 1 simplification:
///         - Single base asset (USDC). Multi-asset handling deferred to v2.
///         - msg.sender is the user. Signature on setMetaStrategy is recorded
///           but not verified — Kite Passport integration stubbed; see
///           docs/kite-passport-notes.md. [PASSPORT-STUB]
///         - withdraw operates against the idle balance held here. Capital
///           that is currently allocated to a strategy lives in the strategy
///           vault and must be unwound through the AllocatorVault first.
///         Helios.md §6.2.
contract UserVault is
    IUserVault,
    Initializable,
    OwnableUpgradeable,
    ReentrancyGuardTransient,
    UUPSUpgradeable
{
    using SafeERC20 for IERC20;

    IERC20 public baseAsset;
    uint64 public maxSessionTTL;

    struct UserState {
        uint256 balance;
        uint256 highWaterMark;
        address allocator;
        uint64 sessionExpiry;
        bool metaSet;
    }

    mapping(address => UserState) internal _users;
    mapping(address => MetaStrategyLib.MetaStrategy) internal _metas;
    // Deprecated PR4: previously stored the [PASSPORT-STUB] signature alongside
    // the meta. Was never read on-chain (verification lives in the off-chain
    // Sentinel REST handler). Slot retained so the UUPS storage layout doesn't
    // shift; the write itself was dropped to save an SSTORE per `setMetaStrategy`.
    mapping(address => bytes) internal _metaSignatures_deprecated;

    /// @notice Per-user allowlist for `MetaStrategy.allowedStrategyClasses`,
    ///         denormalized for O(1) lookup. `AllocatorVault` reads this on
    ///         every allocate/rebalance — populating it once at
    ///         `setMetaStrategy` time saves ~1.5k gas per allocate when the
    ///         user's allowedStrategyClasses ≥ 4.
    mapping(address => mapping(bytes32 => bool)) internal _classAllowed;

    /// @dev Reserved storage for future upgrades. Append new state variables
    ///      ABOVE this gap and shrink it accordingly so storage layout stays compatible.
    uint256[49] private __gap;

    error ZeroAddress();
    error ZeroAmount();
    error UnsupportedAsset();
    error InsufficientBalance();
    error MetaNotSet();
    error MetaAssetNotAllowed();
    error NotDelegatedAllocator();
    error SessionExpired();
    error SessionTTLTooLong();

    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }

    function initialize(IERC20 baseAsset_, uint64 maxSessionTTL_, address owner_)
        external
        initializer
    {
        if (address(baseAsset_) == address(0) || owner_ == address(0)) {
            revert ZeroAddress();
        }
        __Ownable_init(owner_);
        baseAsset = baseAsset_;
        maxSessionTTL = maxSessionTTL_;
    }

    function _authorizeUpgrade(address) internal override onlyOwner { }

    // ── Meta-strategy ───────────────────────────────────────────────

    /// @notice Records the meta-strategy for msg.sender. The signature is
    ///         carried for forward compat with Kite Passport but is not
    ///         verified in Phase 1 — the user IS the caller. [PASSPORT-STUB]
    function setMetaStrategy(
        MetaStrategyLib.MetaStrategy calldata meta,
        bytes calldata /* signature - PR4: verified off-chain by Sentinel */
    )
        external
    {
        if (meta.maxCapital == 0) revert ZeroAmount();
        // Quick sanity: the base asset should be in the allowed-assets list
        // (or the list should be empty meaning "unrestricted" — for Phase 1
        // an explicit list is preferred).
        if (meta.allowedAssets.length > 0) {
            bool found;
            for (uint256 i = 0; i < meta.allowedAssets.length; i++) {
                if (meta.allowedAssets[i] == address(baseAsset)) {
                    found = true;
                    break;
                }
            }
            if (!found) revert MetaAssetNotAllowed();
        }
        // WS7.C — fill in the auto-defund defaults when the caller passes
        // zero so existing onboarding payloads keep working unchanged.
        MetaStrategyLib.MetaStrategy memory stored = meta;
        if (stored.defundTwapBars == 0) {
            stored.defundTwapBars = MetaStrategyLib.DEFAULT_DEFUND_TWAP_BARS;
        }
        if (stored.defundBondBps == 0) {
            stored.defundBondBps = MetaStrategyLib.DEFAULT_DEFUND_BOND_BPS;
        }
        if (stored.defundConfirmBlocks == 0) {
            stored.defundConfirmBlocks = MetaStrategyLib.DEFAULT_DEFUND_CONFIRM_BLOCKS;
        }
        // Refresh the denormalized class-allowlist mapping. Clear the
        // previous entries (if re-setting) before writing the new ones so
        // a removed class doesn't linger.
        bytes32[] storage prev = _metas[msg.sender].allowedStrategyClasses;
        for (uint256 i = 0; i < prev.length; i++) {
            _classAllowed[msg.sender][prev[i]] = false;
        }
        for (uint256 i = 0; i < stored.allowedStrategyClasses.length; i++) {
            _classAllowed[msg.sender][stored.allowedStrategyClasses[i]] = true;
        }
        _metas[msg.sender] = stored;
        _users[msg.sender].metaSet = true;
        emit MetaStrategySet(msg.sender, stored.metaStrategyHash);
    }

    // ── Deposit / Withdraw ──────────────────────────────────────────

    function deposit(address asset, uint256 amount) external nonReentrant {
        if (asset != address(baseAsset)) revert UnsupportedAsset();
        if (amount == 0) revert ZeroAmount();
        IERC20(asset).safeTransferFrom(msg.sender, address(this), amount);
        _users[msg.sender].balance += amount;
        // First-deposit HWM = principal.
        UserState storage u = _users[msg.sender];
        if (u.highWaterMark < u.balance) u.highWaterMark = u.balance;
        emit Deposited(msg.sender, asset, amount);
    }

    function withdraw(address asset, uint256 amount) external nonReentrant {
        if (asset != address(baseAsset)) revert UnsupportedAsset();
        if (amount == 0) revert ZeroAmount();
        UserState storage u = _users[msg.sender];
        if (amount > u.balance) revert InsufficientBalance();
        u.balance -= amount;
        IERC20(asset).safeTransfer(msg.sender, amount);
        emit Withdrawn(msg.sender, asset, amount);
    }

    // ── Allocator delegation ────────────────────────────────────────

    function delegateToAllocator(address allocator, uint64 sessionTTL) external {
        if (allocator == address(0)) revert ZeroAddress();
        if (sessionTTL == 0 || sessionTTL > maxSessionTTL) revert SessionTTLTooLong();
        if (!_users[msg.sender].metaSet) revert MetaNotSet();
        UserState storage u = _users[msg.sender];
        u.allocator = allocator;
        u.sessionExpiry = uint64(block.timestamp) + sessionTTL;
        // sessionKey is reserved for future Passport-issued ephemeral keys; in
        // Phase 1 we just hash the (user, allocator, expiry) tuple as a
        // placeholder so the event index has a stable value. [PASSPORT-STUB]
        bytes32 sessionKey = keccak256(abi.encode(msg.sender, allocator, u.sessionExpiry));
        emit AllocatorDelegated(msg.sender, allocator, sessionTTL, sessionKey);
    }

    // ── AllocatorVault privileged hooks ─────────────────────────────

    function transferToAllocator(address user, uint256 amount) external nonReentrant {
        UserState storage u = _users[user];
        if (msg.sender != u.allocator) revert NotDelegatedAllocator();
        if (block.timestamp > u.sessionExpiry) revert SessionExpired();
        if (amount > u.balance) revert InsufficientBalance();
        u.balance -= amount;
        baseAsset.safeTransfer(msg.sender, amount);
        emit AllocatorTransfer(user, msg.sender, amount, u.balance);
    }

    function creditFromAllocator(address user, uint256 amount) external nonReentrant {
        UserState storage u = _users[user];
        if (msg.sender != u.allocator) revert NotDelegatedAllocator();
        baseAsset.safeTransferFrom(msg.sender, address(this), amount);
        u.balance += amount;
        if (u.balance > u.highWaterMark) u.highWaterMark = u.balance;
        emit AllocatorCredit(user, msg.sender, amount, u.balance, u.highWaterMark);
    }

    // ── Views ───────────────────────────────────────────────────────

    function metaStrategyOf(address user)
        external
        view
        returns (MetaStrategyLib.MetaStrategy memory)
    {
        return _metas[user];
    }

    /// @notice O(1) class-allowlist check. Mirrors a linear scan over
    ///         `metaStrategyOf(user).allowedStrategyClasses` but uses the
    ///         denormalized `_classAllowed` mapping populated at
    ///         `setMetaStrategy` time.
    function isClassAllowedFor(address user, bytes32 classId) external view returns (bool) {
        return _classAllowed[user][classId];
    }

    function allocatorOf(address user) external view returns (address) {
        return _users[user].allocator;
    }

    function highWaterMarkOf(address user) external view returns (uint256) {
        return _users[user].highWaterMark;
    }

    function balanceOf(address user) external view returns (uint256) {
        return _users[user].balance;
    }

    function sessionExpiryOf(address user) external view returns (uint64) {
        return _users[user].sessionExpiry;
    }
}
