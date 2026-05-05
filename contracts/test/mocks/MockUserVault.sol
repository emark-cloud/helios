// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { IERC20 } from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import { SafeERC20 } from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import { MetaStrategyLib } from "../../src/interfaces/IMetaStrategy.sol";

/// @notice Minimal UserVault stand-in for AllocatorVault tests. Holds
///         per-user balances, per-user meta-strategies, per-user delegated
///         allocator. The real UserVault built in WS1 will replace this.
contract MockUserVault {
    using SafeERC20 for IERC20;

    IERC20 public immutable baseAsset;
    mapping(address => uint256) public balanceOf;
    mapping(address => MetaStrategyLib.MetaStrategy) internal _meta;
    mapping(address => address) internal _allocator;
    mapping(address => mapping(bytes32 => bool)) internal _classAllowed;

    constructor(IERC20 baseAsset_) {
        baseAsset = baseAsset_;
    }

    function setMeta(address user, MetaStrategyLib.MetaStrategy calldata meta) external {
        // Refresh denormalized class-allowlist mapping so the real
        // `isClassAllowedFor` view sees the same set of classes.
        bytes32[] storage prev = _meta[user].allowedStrategyClasses;
        for (uint256 i = 0; i < prev.length; i++) {
            _classAllowed[user][prev[i]] = false;
        }
        for (uint256 i = 0; i < meta.allowedStrategyClasses.length; i++) {
            _classAllowed[user][meta.allowedStrategyClasses[i]] = true;
        }
        _meta[user] = meta;
    }

    function setAllocator(address user, address allocator) external {
        _allocator[user] = allocator;
    }

    function deposit(address user, uint256 amount) external {
        baseAsset.safeTransferFrom(msg.sender, address(this), amount);
        balanceOf[user] += amount;
    }

    function transferToAllocator(address user, uint256 amount) external {
        require(msg.sender == _allocator[user], "not user's allocator");
        require(balanceOf[user] >= amount, "insufficient user balance");
        balanceOf[user] -= amount;
        baseAsset.safeTransfer(msg.sender, amount);
    }

    function creditFromAllocator(address user, uint256 amount) external {
        require(msg.sender == _allocator[user], "not user's allocator");
        baseAsset.safeTransferFrom(msg.sender, address(this), amount);
        balanceOf[user] += amount;
    }

    function metaStrategyOf(address user)
        external
        view
        returns (MetaStrategyLib.MetaStrategy memory)
    {
        return _meta[user];
    }

    function isClassAllowedFor(address user, bytes32 classId) external view returns (bool) {
        return _classAllowed[user][classId];
    }

    function allocatorOf(address user) external view returns (address) {
        return _allocator[user];
    }
}
