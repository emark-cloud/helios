// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Test } from "forge-std/Test.sol";
import { StrategyRegistry } from "../src/StrategyRegistry.sol";
import { IStrategyRegistry } from "../src/interfaces/IStrategyRegistry.sol";
import { MockERC20 } from "./mocks/MockERC20.sol";
import { Ownable } from "@openzeppelin/contracts/access/Ownable.sol";

contract StrategyRegistryTest is Test {
    StrategyRegistry internal registry;
    MockERC20 internal stake;

    address internal owner = makeAddr("owner");
    address internal anchor = makeAddr("reputationAnchor");
    address internal operator = makeAddr("operator");
    address internal vault = makeAddr("vault");
    address internal randomCaller = makeAddr("random");

    bytes32 internal constant CLASS_MOMENTUM = keccak256("momentum_v1");
    uint256 internal constant COOLDOWN = 7 days;
    uint256 internal constant STAKE = 10_000e18;

    function setUp() public {
        stake = new MockERC20("Mock USDC", "mUSDC");
        registry = new StrategyRegistry(stake, anchor, owner, COOLDOWN);

        stake.mint(operator, 1_000_000e18);
        vm.prank(operator);
        stake.approve(address(registry), type(uint256).max);
    }

    // ── Constructor ─────────────────────────────────────────────────

    function test_Constructor_SetsImmutables() public view {
        assertEq(address(registry.stakeToken()), address(stake));
        assertEq(registry.reputationAnchor(), anchor);
        assertEq(registry.owner(), owner);
        assertEq(registry.stakeCooldown(), COOLDOWN);
    }

    function test_Constructor_RevertsOnZeroToken() public {
        vm.expectRevert(StrategyRegistry.ZeroAddress.selector);
        new StrategyRegistry(MockERC20(address(0)), anchor, owner, COOLDOWN);
    }

    function test_Constructor_RevertsOnZeroAnchor() public {
        vm.expectRevert(StrategyRegistry.ZeroAddress.selector);
        new StrategyRegistry(stake, address(0), owner, COOLDOWN);
    }

    function test_Constructor_RevertsOnZeroOwner() public {
        // Ownable's own zero-owner guard fires before our explicit check.
        vm.expectRevert(abi.encodeWithSelector(Ownable.OwnableInvalidOwner.selector, address(0)));
        new StrategyRegistry(stake, anchor, address(0), COOLDOWN);
    }

    // ── registerStrategy ────────────────────────────────────────────

    function test_RegisterStrategy_Happy() public {
        vm.expectEmit(true, true, true, true);
        emit IStrategyRegistry.StrategyRegistered(vault, vault, operator, CLASS_MOMENTUM, STAKE);

        vm.prank(operator);
        address id = registry.registerStrategy(vault, CLASS_MOMENTUM, STAKE);

        assertEq(id, vault);
        assertEq(stake.balanceOf(address(registry)), STAKE);
        assertEq(stake.balanceOf(operator), 1_000_000e18 - STAKE);

        IStrategyRegistry.StrategyEntry memory e = registry.strategyOf(vault);
        assertEq(e.vault, vault);
        assertEq(e.operator, operator);
        assertEq(e.declaredClass, CLASS_MOMENTUM);
        assertEq(e.stakeAmount, STAKE);
        assertEq(e.currentReputation, 0);
        assertEq(e.registeredAt, block.timestamp);
        assertTrue(e.active);

        address[] memory byClass = registry.strategiesByClass(CLASS_MOMENTUM);
        assertEq(byClass.length, 1);
        assertEq(byClass[0], vault);
        assertEq(registry.strategyCount(), 1);
    }

    function test_RegisterStrategy_RevertsOnZeroVault() public {
        vm.prank(operator);
        vm.expectRevert(StrategyRegistry.ZeroAddress.selector);
        registry.registerStrategy(address(0), CLASS_MOMENTUM, STAKE);
    }

    function test_RegisterStrategy_RevertsOnZeroStake() public {
        vm.prank(operator);
        vm.expectRevert(StrategyRegistry.ZeroAmount.selector);
        registry.registerStrategy(vault, CLASS_MOMENTUM, 0);
    }

    function test_RegisterStrategy_RevertsOnDuplicate() public {
        vm.prank(operator);
        registry.registerStrategy(vault, CLASS_MOMENTUM, STAKE);

        vm.prank(operator);
        vm.expectRevert(StrategyRegistry.StrategyAlreadyRegistered.selector);
        registry.registerStrategy(vault, CLASS_MOMENTUM, STAKE);
    }

    // ── topUpStake ──────────────────────────────────────────────────

    function test_TopUpStake_Happy() public {
        _register();
        vm.prank(operator);
        registry.topUpStake(vault, 5000e18);

        IStrategyRegistry.StrategyEntry memory e = registry.strategyOf(vault);
        assertEq(e.stakeAmount, STAKE + 5000e18);
    }

    function test_TopUpStake_RevertsOnUnknownStrategy() public {
        vm.prank(operator);
        vm.expectRevert(StrategyRegistry.StrategyNotFound.selector);
        registry.topUpStake(vault, 5000e18);
    }

    function test_TopUpStake_RevertsOnZeroAmount() public {
        _register();
        vm.prank(operator);
        vm.expectRevert(StrategyRegistry.ZeroAmount.selector);
        registry.topUpStake(vault, 0);
    }

    // ── Stake withdrawal (cooldown) ─────────────────────────────────

    function test_StakeWithdrawal_FullCycle() public {
        _register();

        uint64 expectedUnlock = uint64(block.timestamp + COOLDOWN);
        vm.expectEmit(true, false, false, true);
        emit IStrategyRegistry.StakeWithdrawalInitiated(vault, 4000e18, expectedUnlock);

        vm.prank(operator);
        registry.initiateStakeWithdrawal(vault, 4000e18);

        // Cooldown not yet elapsed
        vm.prank(operator);
        vm.expectRevert(IStrategyRegistry.StakeCooldownActive.selector);
        registry.completeStakeWithdrawal(vault);

        skip(COOLDOWN);

        uint256 opBalBefore = stake.balanceOf(operator);
        vm.prank(operator);
        registry.completeStakeWithdrawal(vault);

        assertEq(stake.balanceOf(operator), opBalBefore + 4000e18);
        assertEq(registry.strategyOf(vault).stakeAmount, STAKE - 4000e18);
        (uint256 pendAmt,) = registry.pendingWithdrawals(vault);
        assertEq(pendAmt, 0);
    }

    function test_InitiateWithdrawal_RevertsIfNotOperator() public {
        _register();
        vm.prank(randomCaller);
        vm.expectRevert(IStrategyRegistry.NotOperator.selector);
        registry.initiateStakeWithdrawal(vault, 1000e18);
    }

    function test_InitiateWithdrawal_RevertsIfExceedsStake() public {
        _register();
        vm.prank(operator);
        vm.expectRevert(StrategyRegistry.WithdrawalExceedsStake.selector);
        registry.initiateStakeWithdrawal(vault, STAKE + 1);
    }

    function test_InitiateWithdrawal_RevertsIfAlreadyPending() public {
        _register();
        vm.prank(operator);
        registry.initiateStakeWithdrawal(vault, 1000e18);

        vm.prank(operator);
        vm.expectRevert(StrategyRegistry.WithdrawalAlreadyPending.selector);
        registry.initiateStakeWithdrawal(vault, 1000e18);
    }

    function test_CompleteWithdrawal_RevertsIfNothingPending() public {
        _register();
        vm.prank(operator);
        vm.expectRevert(StrategyRegistry.NoPendingWithdrawal.selector);
        registry.completeStakeWithdrawal(vault);
    }

    // ── deactivate ──────────────────────────────────────────────────

    function test_Deactivate_Happy() public {
        _register();
        vm.expectEmit(true, false, false, false);
        emit IStrategyRegistry.StrategyDeactivated(vault);
        vm.prank(operator);
        registry.deactivate(vault);

        assertFalse(registry.strategyOf(vault).active);
    }

    function test_Deactivate_RevertsIfNotOperator() public {
        _register();
        vm.prank(randomCaller);
        vm.expectRevert(IStrategyRegistry.NotOperator.selector);
        registry.deactivate(vault);
    }

    function test_Deactivate_RevertsIfAlreadyInactive() public {
        _register();
        vm.prank(operator);
        registry.deactivate(vault);

        vm.prank(operator);
        vm.expectRevert(StrategyRegistry.StrategyInactive.selector);
        registry.deactivate(vault);
    }

    // ── updateReputation ────────────────────────────────────────────

    function test_UpdateReputation_OnlyAnchor() public {
        _register();

        vm.expectEmit(true, false, false, true);
        emit IStrategyRegistry.ReputationUpdated(vault, 250, 250);
        vm.prank(anchor);
        registry.updateReputation(vault, 250);

        assertEq(registry.strategyOf(vault).currentReputation, 250);

        // Negative delta moves it back down
        vm.prank(anchor);
        registry.updateReputation(vault, -100);
        assertEq(registry.strategyOf(vault).currentReputation, 150);
    }

    function test_UpdateReputation_RevertsIfNotAnchor() public {
        _register();
        vm.prank(randomCaller);
        vm.expectRevert(IStrategyRegistry.NotReputationAnchor.selector);
        registry.updateReputation(vault, 100);
    }

    // ── slash ───────────────────────────────────────────────────────

    function test_Slash_OnlyOwner_DecrementsStake() public {
        _register();

        vm.expectEmit(true, false, false, true);
        emit IStrategyRegistry.StrategySlashed(vault, 2000e18, "BAD_PROOF");
        vm.prank(owner);
        registry.slash(vault, 2000e18, "BAD_PROOF");

        assertEq(registry.strategyOf(vault).stakeAmount, STAKE - 2000e18);
        assertEq(stake.balanceOf(owner), 2000e18);
    }

    function test_Slash_RevertsIfNotOwner() public {
        _register();
        vm.prank(randomCaller);
        vm.expectRevert(
            abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, randomCaller)
        );
        registry.slash(vault, 1000e18, "x");
    }

    function test_Slash_RevertsIfExceedsStake() public {
        _register();
        vm.prank(owner);
        vm.expectRevert(StrategyRegistry.SlashExceedsStake.selector);
        registry.slash(vault, STAKE + 1, "x");
    }

    // ── Helpers ─────────────────────────────────────────────────────

    function _register() internal {
        vm.prank(operator);
        registry.registerStrategy(vault, CLASS_MOMENTUM, STAKE);
    }
}
