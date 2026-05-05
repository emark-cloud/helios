// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Test } from "forge-std/Test.sol";
import { ClassIds } from "../src/ClassIds.sol";
import { AllocatorRegistry } from "../src/AllocatorRegistry.sol";
import { IAllocatorRegistry } from "../src/interfaces/IAllocatorRegistry.sol";
import { MockERC20 } from "./mocks/MockERC20.sol";
import { Ownable } from "@openzeppelin/contracts/access/Ownable.sol";

contract AllocatorRegistryTest is Test {
    AllocatorRegistry internal registry;
    MockERC20 internal stake;

    address internal owner = makeAddr("owner");
    address internal anchor = makeAddr("reputationAnchor");
    address internal operator = makeAddr("operator");
    address internal vault = makeAddr("operatorVault");
    address internal randomCaller = makeAddr("random");

    bytes32 internal constant CLASS_MOMENTUM = ClassIds.MOMENTUM_V1;
    uint256 internal constant COOLDOWN = 7 days;
    uint256 internal constant STAKE = 25_000e18;
    uint16 internal constant FEE_BPS = 400;

    function setUp() public {
        stake = new MockERC20("Mock USDC", "mUSDC");
        registry = new AllocatorRegistry(stake, anchor, owner, COOLDOWN);

        stake.mint(operator, 1_000_000e18);
        vm.prank(operator);
        stake.approve(address(registry), type(uint256).max);
    }

    function _supportedClasses() internal pure returns (bytes32[] memory out) {
        out = new bytes32[](1);
        out[0] = CLASS_MOMENTUM;
    }

    function _register(string memory name) internal returns (address id) {
        vm.prank(operator);
        id = registry.registerAllocator(
            name, vault, bytes32(uint256(0xabc)), _supportedClasses(), FEE_BPS, STAKE
        );
    }

    // ── Constructor ─────────────────────────────────────────────────

    function test_Constructor_SetsImmutables() public view {
        assertEq(address(registry.stakeToken()), address(stake));
        assertEq(registry.reputationAnchor(), anchor);
        assertEq(registry.owner(), owner);
        assertEq(registry.stakeCooldown(), COOLDOWN);
    }

    function test_Constructor_PreSeedsReferenceBrandReservations() public view {
        assertTrue(registry.isNameReserved("Helios Sentinel"));
        assertTrue(registry.isNameReserved("helios sentinel"));
        assertTrue(registry.isNameReserved("HELIOS HELIX"));
        assertFalse(registry.isNameReserved("VolatilityAware"));
    }

    function test_Constructor_RevertsOnZeroToken() public {
        vm.expectRevert(AllocatorRegistry.ZeroAddress.selector);
        new AllocatorRegistry(MockERC20(address(0)), anchor, owner, COOLDOWN);
    }

    function test_Constructor_RevertsOnZeroAnchor() public {
        vm.expectRevert(AllocatorRegistry.ZeroAddress.selector);
        new AllocatorRegistry(stake, address(0), owner, COOLDOWN);
    }

    // ── registerAllocator ───────────────────────────────────────────

    function test_RegisterAllocator_Happy() public {
        address id = _register("VolatilityAware");

        assertEq(id, vault);
        assertEq(stake.balanceOf(address(registry)), STAKE);

        IAllocatorRegistry.AllocatorEntry memory e = registry.allocatorOf(vault);
        assertEq(e.name, "VolatilityAware");
        assertEq(e.operatorVault, vault);
        assertEq(e.operator, operator);
        assertEq(e.feeRateBps, FEE_BPS);
        assertEq(e.stakeAmount, STAKE);
        assertEq(e.currentReputation, 0);
        assertTrue(e.active);
        assertFalse(e.isReferenceBrand);
        assertEq(e.supportedClasses.length, 1);
        assertEq(e.supportedClasses[0], CLASS_MOMENTUM);

        assertEq(registry.allocatorByName("VolatilityAware"), vault);
        assertEq(registry.allocatorByName("volatilityaware"), vault); // case-insensitive lookup
        assertEq(registry.allocatorCount(), 1);
    }

    function test_RegisterAllocator_RevertsOnReservedName() public {
        vm.prank(operator);
        vm.expectRevert(IAllocatorRegistry.ReservedName.selector);
        registry.registerAllocator(
            "Helios Sentinel", vault, bytes32(uint256(1)), _supportedClasses(), FEE_BPS, STAKE
        );

        vm.prank(operator);
        vm.expectRevert(IAllocatorRegistry.ReservedName.selector);
        registry.registerAllocator(
            "helios sentinel", vault, bytes32(uint256(1)), _supportedClasses(), FEE_BPS, STAKE
        );
    }

    function test_RegisterAllocator_RevertsOnDuplicateName() public {
        _register("Sigma");
        address otherVault = makeAddr("other");
        // Same name, different vault
        vm.prank(operator);
        vm.expectRevert(AllocatorRegistry.NameAlreadyTaken.selector);
        registry.registerAllocator(
            "sigma", otherVault, bytes32(0), _supportedClasses(), FEE_BPS, STAKE
        );
    }

    function test_RegisterAllocator_RevertsOnDuplicateVault() public {
        _register("First");
        vm.prank(operator);
        vm.expectRevert(AllocatorRegistry.AllocatorAlreadyRegistered.selector);
        registry.registerAllocator("Second", vault, bytes32(0), _supportedClasses(), FEE_BPS, STAKE);
    }

    function test_RegisterAllocator_RevertsOnZeroVault() public {
        vm.prank(operator);
        vm.expectRevert(AllocatorRegistry.ZeroAddress.selector);
        registry.registerAllocator("X", address(0), bytes32(0), _supportedClasses(), FEE_BPS, STAKE);
    }

    function test_RegisterAllocator_RevertsOnZeroStake() public {
        vm.prank(operator);
        vm.expectRevert(AllocatorRegistry.ZeroAmount.selector);
        registry.registerAllocator("X", vault, bytes32(0), _supportedClasses(), FEE_BPS, 0);
    }

    function test_RegisterAllocator_RevertsOnEmptyName() public {
        vm.prank(operator);
        vm.expectRevert(AllocatorRegistry.EmptyName.selector);
        registry.registerAllocator("", vault, bytes32(0), _supportedClasses(), FEE_BPS, STAKE);
    }

    // ── reserveName + assignReferenceBrand ──────────────────────────

    function test_ReserveName_OwnerOnly() public {
        vm.prank(owner);
        registry.reserveName("Helios Beam");
        assertTrue(registry.isNameReserved("helios beam"));
    }

    function test_ReserveName_RevertsIfNotOwner() public {
        vm.prank(randomCaller);
        vm.expectRevert(
            abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, randomCaller)
        );
        registry.reserveName("Helios Beam");
    }

    function test_ReserveName_AllowsReservingHeldName_LocksFutureRegistrations() public {
        _register("Sigma");
        vm.prank(owner);
        registry.reserveName("sigma");
        assertTrue(registry.isNameReserved("sigma"));

        // A new allocator trying to claim "sigma" after deactivation now reverts.
        vm.prank(operator);
        registry.deactivate(vault);

        address otherVault = makeAddr("otherVault");
        vm.prank(operator);
        vm.expectRevert(IAllocatorRegistry.ReservedName.selector);
        registry.registerAllocator(
            "Sigma", otherVault, bytes32(0), _supportedClasses(), FEE_BPS, STAKE
        );
    }

    function test_ReserveName_RevertsOnEmpty() public {
        vm.prank(owner);
        vm.expectRevert(AllocatorRegistry.EmptyName.selector);
        registry.reserveName("");
    }

    function test_AssignReferenceBrand_Flow() public {
        // Operator pre-reserves a "Helios *" registration ahead of brand assignment by:
        // 1. owner reserves a name first
        // 2. owner relaxes by deleting? No — actually, the spec says reference brands
        //    use reserved names assigned to a multi-sig-approved allocator.
        // Real flow: owner reserves "Helios Demo", then registers an allocator
        // address (msg.sender == owner here for simplicity) — but registration
        // would revert because the name is reserved. So in production the owner
        // unreserves, registers, re-reserves. For the test we exercise the
        // happy path: reserve a name AFTER registration, then assign.
        _register("Helios Demo");
        vm.prank(owner);
        registry.reserveName("Helios Demo");

        vm.expectEmit(true, false, false, false);
        emit IAllocatorRegistry.ReferenceBrandAssigned(vault);
        vm.prank(owner);
        registry.assignReferenceBrand(vault);

        assertTrue(registry.allocatorOf(vault).isReferenceBrand);
    }

    function test_AssignReferenceBrand_RevertsIfNameNotReserved() public {
        _register("Plain");
        vm.prank(owner);
        vm.expectRevert(AllocatorRegistry.NameNotReserved.selector);
        registry.assignReferenceBrand(vault);
    }

    function test_AssignReferenceBrand_RevertsIfNotOwner() public {
        _register("Sigma");
        vm.prank(randomCaller);
        vm.expectRevert(
            abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, randomCaller)
        );
        registry.assignReferenceBrand(vault);
    }

    function test_AssignReferenceBrand_RevertsIfUnknown() public {
        vm.prank(owner);
        vm.expectRevert(AllocatorRegistry.AllocatorNotFound.selector);
        registry.assignReferenceBrand(makeAddr("ghost"));
    }

    // ── Stake management ────────────────────────────────────────────

    function test_TopUpStake_Happy() public {
        _register("Sigma");
        vm.prank(operator);
        registry.topUpStake(vault, 5000e18);
        assertEq(registry.allocatorOf(vault).stakeAmount, STAKE + 5000e18);
    }

    function test_StakeWithdrawal_FullCycle() public {
        _register("Sigma");

        vm.prank(operator);
        registry.initiateStakeWithdrawal(vault, 4000e18);

        vm.prank(operator);
        vm.expectRevert(AllocatorRegistry.StakeCooldownActive.selector);
        registry.completeStakeWithdrawal(vault);

        skip(COOLDOWN);

        uint256 balBefore = stake.balanceOf(operator);
        vm.prank(operator);
        registry.completeStakeWithdrawal(vault);

        assertEq(stake.balanceOf(operator), balBefore + 4000e18);
        assertEq(registry.allocatorOf(vault).stakeAmount, STAKE - 4000e18);
    }

    function test_InitiateWithdrawal_RevertsIfNotOperator() public {
        _register("Sigma");
        vm.prank(randomCaller);
        vm.expectRevert(IAllocatorRegistry.NotAllocatorOperator.selector);
        registry.initiateStakeWithdrawal(vault, 1000e18);
    }

    function test_InitiateWithdrawal_RevertsIfExceedsStake() public {
        _register("Sigma");
        vm.prank(operator);
        vm.expectRevert(AllocatorRegistry.WithdrawalExceedsStake.selector);
        registry.initiateStakeWithdrawal(vault, STAKE + 1);
    }

    function test_InitiateWithdrawal_RevertsIfAlreadyPending() public {
        _register("Sigma");
        vm.prank(operator);
        registry.initiateStakeWithdrawal(vault, 1000e18);
        vm.prank(operator);
        vm.expectRevert(AllocatorRegistry.WithdrawalAlreadyPending.selector);
        registry.initiateStakeWithdrawal(vault, 1000e18);
    }

    function test_CompleteWithdrawal_RevertsIfNothingPending() public {
        _register("Sigma");
        vm.prank(operator);
        vm.expectRevert(AllocatorRegistry.NoPendingWithdrawal.selector);
        registry.completeStakeWithdrawal(vault);
    }

    // ── Deactivate ──────────────────────────────────────────────────

    function test_Deactivate_Happy() public {
        _register("Sigma");
        vm.prank(operator);
        registry.deactivate(vault);
        assertFalse(registry.allocatorOf(vault).active);
    }

    function test_Deactivate_RevertsIfNotOperator() public {
        _register("Sigma");
        vm.prank(randomCaller);
        vm.expectRevert(IAllocatorRegistry.NotAllocatorOperator.selector);
        registry.deactivate(vault);
    }

    function test_Deactivate_RevertsIfAlreadyInactive() public {
        _register("Sigma");
        vm.prank(operator);
        registry.deactivate(vault);
        vm.prank(operator);
        vm.expectRevert(AllocatorRegistry.AllocatorInactive.selector);
        registry.deactivate(vault);
    }

    // ── Reputation + slashing ───────────────────────────────────────

    function test_UpdateReputation_OnlyAnchor() public {
        _register("Sigma");
        vm.prank(anchor);
        registry.updateReputation(vault, 500);
        assertEq(registry.allocatorOf(vault).currentReputation, 500);

        vm.prank(anchor);
        registry.updateReputation(vault, -200);
        assertEq(registry.allocatorOf(vault).currentReputation, 300);
    }

    function test_UpdateReputation_RevertsIfNotAnchor() public {
        _register("Sigma");
        vm.prank(randomCaller);
        vm.expectRevert(IAllocatorRegistry.NotReputationAnchor.selector);
        registry.updateReputation(vault, 100);
    }

    function test_Slash_OnlyOwner_DecrementsStake() public {
        _register("Sigma");
        vm.prank(owner);
        registry.slash(vault, 5000e18, "BAD_RANK");
        assertEq(registry.allocatorOf(vault).stakeAmount, STAKE - 5000e18);
        assertEq(stake.balanceOf(owner), 5000e18);
    }

    function test_Slash_RevertsIfNotOwner() public {
        _register("Sigma");
        vm.prank(randomCaller);
        vm.expectRevert(
            abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, randomCaller)
        );
        registry.slash(vault, 1000e18, "x");
    }

    function test_Slash_RevertsIfExceedsStake() public {
        _register("Sigma");
        vm.prank(owner);
        vm.expectRevert(AllocatorRegistry.SlashExceedsStake.selector);
        registry.slash(vault, STAKE + 1, "x");
    }

    function test_Slash_ToZeroDeactivates() public {
        _register("Sigma");
        assertTrue(registry.allocatorOf(vault).active);

        vm.prank(owner);
        registry.slash(vault, STAKE, "FULL_STAKE");

        IAllocatorRegistry.AllocatorEntry memory a = registry.allocatorOf(vault);
        assertEq(a.stakeAmount, 0);
        assertFalse(a.active);
    }

    function test_Slash_PartialKeepsActive() public {
        _register("Sigma");

        vm.prank(owner);
        registry.slash(vault, STAKE - 1, "PARTIAL");

        IAllocatorRegistry.AllocatorEntry memory a = registry.allocatorOf(vault);
        assertEq(a.stakeAmount, 1);
        assertTrue(a.active);
    }
}
