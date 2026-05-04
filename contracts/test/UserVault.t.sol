// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Test } from "forge-std/Test.sol";
import { ClassIds } from "../src/ClassIds.sol";
import { UserVault } from "../src/UserVault.sol";
import { IUserVault } from "../src/interfaces/IUserVault.sol";
import { MetaStrategyLib } from "../src/interfaces/IMetaStrategy.sol";
import { MockERC20 } from "./mocks/MockERC20.sol";
import { ERC1967Proxy } from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";

contract UserVaultTest is Test {
    UserVault internal vault;
    MockERC20 internal usdc;

    address internal owner = makeAddr("owner");
    address internal user = makeAddr("user");
    address internal allocator = makeAddr("allocator");
    address internal randomCaller = makeAddr("rando");

    uint64 internal constant MAX_SESSION_TTL = 30 days;
    uint256 internal constant DEPOSIT = 50_000e6;

    event MetaStrategySet(address indexed user, bytes32 indexed metaStrategyHash);
    event Deposited(address indexed user, address indexed asset, uint256 amount);
    event AllocatorDelegated(
        address indexed user, address indexed allocator, uint64 sessionTTL, bytes32 sessionKey
    );
    event AllocatorFeeSettled(
        address indexed user, address indexed allocator, uint256 feeAmount, uint256 newHighWaterMark
    );
    event Withdrawn(address indexed user, address indexed asset, uint256 amount);

    function setUp() public {
        usdc = new MockERC20("USDC", "USDC");
        UserVault impl = new UserVault();
        bytes memory init = abi.encodeCall(UserVault.initialize, (usdc, MAX_SESSION_TTL, owner));
        vault = UserVault(address(new ERC1967Proxy(address(impl), init)));

        usdc.mint(user, DEPOSIT * 2);
        vm.prank(user);
        usdc.approve(address(vault), type(uint256).max);
    }

    function _meta() internal view returns (MetaStrategyLib.MetaStrategy memory m) {
        bytes32[] memory classes = new bytes32[](1);
        classes[0] = ClassIds.MOMENTUM_V1;
        address[] memory allowed = new address[](1);
        allowed[0] = address(usdc);
        uint32[] memory chains = new uint32[](1);
        chains[0] = uint32(block.chainid);
        m = MetaStrategyLib.MetaStrategy({
            metaStrategyHash: keccak256("hello"),
            allowedStrategyClasses: classes,
            allowedAssets: allowed,
            allowedChains: chains,
            maxCapital: DEPOSIT,
            maxPerStrategyBps: 6000,
            maxStrategiesCount: 3,
            drawdownThresholdBps: 1500,
            maxFeeRateBps: 2500,
            rebalanceCadenceSec: 1 days,
            validUntil: uint64(block.timestamp + 30 days),
            defundTwapBars: 5,
            defundBondBps: 100,
            defundConfirmBlocks: 50
        });
    }

    // ── setMetaStrategy ─────────────────────────────────────────────

    function test_SetMetaStrategy_HappyPath() public {
        MetaStrategyLib.MetaStrategy memory m = _meta();
        vm.expectEmit(true, true, false, false);
        emit MetaStrategySet(user, m.metaStrategyHash);
        vm.prank(user);
        vault.setMetaStrategy(m, hex"deadbeef");

        MetaStrategyLib.MetaStrategy memory stored = vault.metaStrategyOf(user);
        assertEq(stored.metaStrategyHash, m.metaStrategyHash);
        assertEq(stored.maxCapital, m.maxCapital);
    }

    function test_SetMetaStrategy_RevertsOnZeroCapital() public {
        MetaStrategyLib.MetaStrategy memory m = _meta();
        m.maxCapital = 0;
        vm.prank(user);
        vm.expectRevert(UserVault.ZeroAmount.selector);
        vault.setMetaStrategy(m, "");
    }

    function test_SetMetaStrategy_RevertsOnDisallowedBaseAsset() public {
        MetaStrategyLib.MetaStrategy memory m = _meta();
        address[] memory other = new address[](1);
        other[0] = makeAddr("notUsdc");
        m.allowedAssets = other;
        vm.prank(user);
        vm.expectRevert(UserVault.MetaAssetNotAllowed.selector);
        vault.setMetaStrategy(m, "");
    }

    /// WS7.C — explicit non-zero defund knobs round-trip through storage.
    function test_SetMetaStrategy_RoundTripsDefundFields() public {
        MetaStrategyLib.MetaStrategy memory m = _meta();
        vm.prank(user);
        vault.setMetaStrategy(m, "");

        MetaStrategyLib.MetaStrategy memory stored = vault.metaStrategyOf(user);
        assertEq(stored.defundTwapBars, 5);
        assertEq(stored.defundBondBps, 100);
        assertEq(stored.defundConfirmBlocks, 50);
    }

    /// WS7.C — zero defund inputs are replaced by the spec defaults so that
    /// onboarding payloads built before the field existed keep working.
    function test_SetMetaStrategy_AppliesDefundDefaultsWhenZero() public {
        MetaStrategyLib.MetaStrategy memory m = _meta();
        m.defundTwapBars = 0;
        m.defundBondBps = 0;
        m.defundConfirmBlocks = 0;
        vm.prank(user);
        vault.setMetaStrategy(m, "");

        MetaStrategyLib.MetaStrategy memory stored = vault.metaStrategyOf(user);
        assertEq(stored.defundTwapBars, MetaStrategyLib.DEFAULT_DEFUND_TWAP_BARS);
        assertEq(stored.defundBondBps, MetaStrategyLib.DEFAULT_DEFUND_BOND_BPS);
        assertEq(stored.defundConfirmBlocks, MetaStrategyLib.DEFAULT_DEFUND_CONFIRM_BLOCKS);
    }

    // ── deposit ─────────────────────────────────────────────────────

    function test_Deposit_RevertsOnUnsupportedAsset() public {
        MockERC20 dai = new MockERC20("DAI", "DAI");
        vm.prank(user);
        vm.expectRevert(UserVault.UnsupportedAsset.selector);
        vault.deposit(address(dai), 1);
    }

    function test_Deposit_RevertsOnZeroAmount() public {
        vm.prank(user);
        vm.expectRevert(UserVault.ZeroAmount.selector);
        vault.deposit(address(usdc), 0);
    }

    function test_Deposit_HappyPath() public {
        vm.expectEmit(true, true, false, true);
        emit Deposited(user, address(usdc), DEPOSIT);
        vm.prank(user);
        vault.deposit(address(usdc), DEPOSIT);
        assertEq(vault.balanceOf(user), DEPOSIT);
        assertEq(vault.highWaterMarkOf(user), DEPOSIT);
        assertEq(usdc.balanceOf(address(vault)), DEPOSIT);
    }

    // ── withdraw ────────────────────────────────────────────────────

    function test_Withdraw_RevertsOnInsufficientBalance() public {
        vm.prank(user);
        vm.expectRevert(UserVault.InsufficientBalance.selector);
        vault.withdraw(address(usdc), 1);
    }

    function test_Withdraw_HappyPath() public {
        vm.startPrank(user);
        vault.deposit(address(usdc), DEPOSIT);
        uint256 before = usdc.balanceOf(user);
        vm.expectEmit(true, true, false, true);
        emit Withdrawn(user, address(usdc), 10_000e6);
        vault.withdraw(address(usdc), 10_000e6);
        vm.stopPrank();
        assertEq(usdc.balanceOf(user) - before, 10_000e6);
        assertEq(vault.balanceOf(user), DEPOSIT - 10_000e6);
    }

    // ── delegateToAllocator ─────────────────────────────────────────

    function test_DelegateToAllocator_RevertsWithoutMeta() public {
        vm.prank(user);
        vm.expectRevert(UserVault.MetaNotSet.selector);
        vault.delegateToAllocator(allocator, 1 days);
    }

    function test_DelegateToAllocator_RevertsOnZeroTTL() public {
        vm.prank(user);
        vault.setMetaStrategy(_meta(), "");
        vm.prank(user);
        vm.expectRevert(UserVault.SessionTTLTooLong.selector);
        vault.delegateToAllocator(allocator, 0);
    }

    function test_DelegateToAllocator_RevertsOnTTLOverMax() public {
        vm.prank(user);
        vault.setMetaStrategy(_meta(), "");
        vm.prank(user);
        vm.expectRevert(UserVault.SessionTTLTooLong.selector);
        vault.delegateToAllocator(allocator, MAX_SESSION_TTL + 1);
    }

    function test_DelegateToAllocator_HappyPath() public {
        vm.prank(user);
        vault.setMetaStrategy(_meta(), "");
        vm.expectEmit(true, true, false, false);
        emit AllocatorDelegated(user, allocator, 7 days, bytes32(0));
        vm.prank(user);
        vault.delegateToAllocator(allocator, 7 days);
        assertEq(vault.allocatorOf(user), allocator);
        assertEq(vault.sessionExpiryOf(user), uint64(block.timestamp + 7 days));
    }

    // ── transferToAllocator (privileged) ────────────────────────────

    function _seedDelegation() internal {
        vm.prank(user);
        vault.setMetaStrategy(_meta(), "");
        vm.prank(user);
        vault.deposit(address(usdc), DEPOSIT);
        vm.prank(user);
        vault.delegateToAllocator(allocator, 7 days);
    }

    function test_TransferToAllocator_OnlyAllocator() public {
        _seedDelegation();
        vm.prank(randomCaller);
        vm.expectRevert(UserVault.NotDelegatedAllocator.selector);
        vault.transferToAllocator(user, 1000e6);
    }

    function test_TransferToAllocator_RevertsOnExpiredSession() public {
        _seedDelegation();
        vm.warp(block.timestamp + 8 days);
        vm.prank(allocator);
        vm.expectRevert(UserVault.SessionExpired.selector);
        vault.transferToAllocator(user, 1000e6);
    }

    function test_TransferToAllocator_RevertsOnInsufficientBalance() public {
        _seedDelegation();
        vm.prank(allocator);
        vm.expectRevert(UserVault.InsufficientBalance.selector);
        vault.transferToAllocator(user, DEPOSIT + 1);
    }

    function test_TransferToAllocator_HappyPath() public {
        _seedDelegation();
        vm.prank(allocator);
        vault.transferToAllocator(user, 20_000e6);
        assertEq(vault.balanceOf(user), DEPOSIT - 20_000e6);
        assertEq(usdc.balanceOf(allocator), 20_000e6);
    }

    // ── creditFromAllocator (privileged) ────────────────────────────

    function test_CreditFromAllocator_OnlyAllocator() public {
        _seedDelegation();
        usdc.mint(randomCaller, 1000e6);
        vm.prank(randomCaller);
        usdc.approve(address(vault), type(uint256).max);
        vm.prank(randomCaller);
        vm.expectRevert(UserVault.NotDelegatedAllocator.selector);
        vault.creditFromAllocator(user, 1000e6);
    }

    function test_CreditFromAllocator_BumpsBalanceAndHWM() public {
        _seedDelegation();
        // Allocator returns capital + profit.
        usdc.mint(allocator, 5000e6);
        vm.prank(allocator);
        usdc.approve(address(vault), type(uint256).max);
        vm.prank(allocator);
        vault.creditFromAllocator(user, 5000e6);
        assertEq(vault.balanceOf(user), DEPOSIT + 5000e6);
        assertEq(vault.highWaterMarkOf(user), DEPOSIT + 5000e6);
    }

    // ── settleAllocatorFee ──────────────────────────────────────────

    function test_SettleAllocatorFee_RevertsOnWrongAllocator() public {
        _seedDelegation();
        vm.prank(user);
        vm.expectRevert(UserVault.NotDelegatedAllocator.selector);
        vault.settleAllocatorFee(randomCaller);
    }

    function test_SettleAllocatorFee_NoOpEmitsZeroFee() public {
        _seedDelegation();
        vm.expectEmit(true, true, false, true);
        emit AllocatorFeeSettled(user, allocator, 0, DEPOSIT);
        vm.prank(user);
        vault.settleAllocatorFee(allocator);
    }
}
