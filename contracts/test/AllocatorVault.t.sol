// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Test } from "forge-std/Test.sol";
import { AllocatorVault } from "../src/AllocatorVault.sol";
import { IAllocatorVault } from "../src/interfaces/IAllocatorVault.sol";
import { StrategyVault } from "../src/StrategyVault.sol";
import { IStrategyVault } from "../src/interfaces/IStrategyVault.sol";
import { StrategyRegistry } from "../src/StrategyRegistry.sol";
import { TradeAttestationVerifier } from "../src/TradeAttestationVerifier.sol";
import { MockERC20 } from "./mocks/MockERC20.sol";
import { MockGroth16Verifier } from "./mocks/MockGroth16Verifier.sol";
import { MockUserVault } from "./mocks/MockUserVault.sol";
import { MetaStrategyLib } from "../src/interfaces/IMetaStrategy.sol";
import { ERC1967Proxy } from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";

contract AllocatorVaultTest is Test {
    AllocatorVault internal allocatorVault;
    StrategyVault internal stratA;
    StrategyVault internal stratB;
    StrategyRegistry internal registry;
    TradeAttestationVerifier internal verifier;
    MockGroth16Verifier internal classVerifier;
    MockERC20 internal usdc;
    MockUserVault internal userVault;

    address internal owner = makeAddr("owner");
    address internal operator = makeAddr("operator");
    address internal stratAOperator = makeAddr("stratAOp");
    address internal stratBOperator = makeAddr("stratBOp");
    address internal navOracle;
    uint256 internal navOracleKey;
    address internal allowedRouter = makeAddr("router");
    address internal user = makeAddr("user");
    address internal randomCaller = makeAddr("rando");

    bytes32 internal constant CLASS_MOM = keccak256("momentum_v1");
    bytes32 internal constant CLASS_MR = keccak256("mean_reversion_v1");
    uint16 internal constant ALLOCATOR_FEE_BPS = 500; // 5%
    uint16 internal constant STRAT_FEE_BPS = 1000; // 10%
    uint16 internal constant DD_THRESHOLD_BPS = 1500; // 15%
    uint256 internal constant USER_DEPOSIT = 100_000e6; // 100k USDC

    event AllocationCreated(
        address indexed user, address indexed strategy, uint256 amount, uint32 chainId
    );
    event AllocationIncreased(address indexed user, address indexed strategy, uint256 delta);
    event AllocationDecreased(address indexed user, address indexed strategy, uint256 delta);
    event StrategyDefunded(
        address indexed user, address indexed strategy, string reason, address indexed triggeredBy
    );
    event StrategyFeeSettled(
        address indexed user, address indexed strategy, uint256 feeAmount, uint256 newHighWaterMark
    );
    event AllocatorFeesWithdrawn(address indexed allocator, uint256 amount);

    function setUp() public {
        (navOracle, navOracleKey) = makeAddrAndKey("navOracle");
        usdc = new MockERC20("USDC", "USDC");
        userVault = new MockUserVault(usdc);

        // Reputation anchor stub & registry
        address reputationAnchor = makeAddr("repAnchor");
        registry = new StrategyRegistry(usdc, reputationAnchor, owner, 7 days);

        verifier = new TradeAttestationVerifier(owner);
        classVerifier = new MockGroth16Verifier(true);
        vm.prank(owner);
        verifier.registerVerifier(CLASS_MOM, address(classVerifier));
        vm.prank(owner);
        verifier.registerVerifier(CLASS_MR, address(classVerifier));

        // Deploy AllocatorVault behind proxy.
        AllocatorVault avImpl = new AllocatorVault();
        bytes memory avInit = abi.encodeCall(
            AllocatorVault.initialize,
            (usdc, operator, address(userVault), address(registry), ALLOCATOR_FEE_BPS, owner)
        );
        allocatorVault = AllocatorVault(address(new ERC1967Proxy(address(avImpl), avInit)));

        // Deploy two strategy vaults paired with this allocator.
        stratA = _deployStrategy(stratAOperator, CLASS_MOM);
        stratB = _deployStrategy(stratBOperator, CLASS_MR);

        // Register the strategies in the registry. Their operators stake.
        usdc.mint(stratAOperator, 5000e6);
        vm.startPrank(stratAOperator);
        usdc.approve(address(registry), type(uint256).max);
        registry.registerStrategy(address(stratA), CLASS_MOM, 5000e6);
        vm.stopPrank();
        usdc.mint(stratBOperator, 5000e6);
        vm.startPrank(stratBOperator);
        usdc.approve(address(registry), type(uint256).max);
        registry.registerStrategy(address(stratB), CLASS_MR, 5000e6);
        vm.stopPrank();

        // Set up the user: meta-strategy, delegate to allocator, deposit USDC.
        bytes32[] memory classes = new bytes32[](2);
        classes[0] = CLASS_MOM;
        classes[1] = CLASS_MR;
        address[] memory allowedAssets = new address[](1);
        allowedAssets[0] = address(usdc);
        uint32[] memory allowedChains = new uint32[](1);
        allowedChains[0] = uint32(block.chainid);
        userVault.setMeta(
            user,
            MetaStrategyLib.MetaStrategy({
                metaStrategyHash: bytes32(uint256(1)),
                allowedStrategyClasses: classes,
                allowedAssets: allowedAssets,
                allowedChains: allowedChains,
                maxCapital: USER_DEPOSIT,
                maxPerStrategyBps: 6000, // 60%
                maxStrategiesCount: 3,
                drawdownThresholdBps: DD_THRESHOLD_BPS,
                maxFeeRateBps: 2500,
                rebalanceCadenceSec: 1 days,
                validUntil: uint64(block.timestamp + 30 days)
            })
        );
        userVault.setAllocator(user, address(allocatorVault));
        usdc.mint(address(this), USER_DEPOSIT);
        usdc.approve(address(userVault), USER_DEPOSIT);
        userVault.deposit(user, USER_DEPOSIT);
    }

    function _deployStrategy(address stratOp, bytes32 declaredClass)
        internal
        returns (StrategyVault s)
    {
        StrategyVault impl = new StrategyVault();
        address[] memory universe = new address[](1);
        universe[0] = address(usdc);
        IStrategyVault.StrategyManifest memory m = IStrategyVault.StrategyManifest({
            declaredClass: declaredClass,
            assetUniverse: universe,
            maxCapacity: 1_000_000e6,
            feeRateBps: STRAT_FEE_BPS,
            operator: stratOp,
            stakeAmount: 5000e6,
            paramsHash: bytes32(0)
        });
        bytes memory initData = abi.encodeCall(
            StrategyVault.initialize,
            (
                m,
                usdc,
                address(registry),
                address(verifier),
                allowedRouter,
                navOracle,
                address(0),
                owner
            )
        );
        // The strategy vault needs the AllocatorVault address as its allocator
        // peer. We may not yet know that address before deployment in the real
        // case (paired in DeployPhase1.s.sol), but in tests we already do.
        initData = abi.encodeCall(
            StrategyVault.initialize,
            (
                m,
                usdc,
                address(registry),
                address(verifier),
                allowedRouter,
                navOracle,
                address(allocatorVault),
                owner
            )
        );
        s = StrategyVault(address(new ERC1967Proxy(address(impl), initData)));
    }

    // ── Initialize ──────────────────────────────────────────────────

    function test_Initialize_RevertsOnZeroOperator() public {
        AllocatorVault freshImpl = new AllocatorVault();
        bytes memory init = abi.encodeCall(
            AllocatorVault.initialize,
            (usdc, address(0), address(userVault), address(registry), ALLOCATOR_FEE_BPS, owner)
        );
        vm.expectRevert();
        new ERC1967Proxy(address(freshImpl), init);
    }

    // ── allocateToStrategy ──────────────────────────────────────────

    function test_AllocateToStrategy_OnlyOperator() public {
        vm.prank(randomCaller);
        vm.expectRevert(IAllocatorVault.NotAllocator.selector);
        allocatorVault.allocateToStrategy(user, address(stratA), 1);
    }

    function test_AllocateToStrategy_ZeroAmountReverts() public {
        vm.prank(operator);
        vm.expectRevert(AllocatorVault.ZeroAmount.selector);
        allocatorVault.allocateToStrategy(user, address(stratA), 0);
    }

    function test_AllocateToStrategy_HappyPath() public {
        vm.expectEmit(true, true, false, true);
        emit AllocationCreated(user, address(stratA), 30_000e6, uint32(block.chainid));
        vm.prank(operator);
        allocatorVault.allocateToStrategy(user, address(stratA), 30_000e6);

        IAllocatorVault.AllocationRecord memory r =
            allocatorVault.allocationOf(user, address(stratA));
        assertEq(r.strategy, address(stratA));
        assertEq(r.capitalDeployed, 30_000e6);
        assertEq(r.strategyHighWaterMark, 30_000e6);
        assertEq(r.defundedAt, 0);
        assertEq(stratA.allocationOf(address(allocatorVault)), 30_000e6);
        assertEq(usdc.balanceOf(address(stratA)), 30_000e6);
        assertEq(userVault.balanceOf(user), USER_DEPOSIT - 30_000e6);
    }

    function test_AllocateToStrategy_TopUpEmitsIncrease() public {
        vm.startPrank(operator);
        allocatorVault.allocateToStrategy(user, address(stratA), 10_000e6);
        vm.expectEmit(true, true, false, true);
        emit AllocationIncreased(user, address(stratA), 5000e6);
        allocatorVault.allocateToStrategy(user, address(stratA), 5000e6);
        vm.stopPrank();
        assertEq(allocatorVault.allocationOf(user, address(stratA)).capitalDeployed, 15_000e6);
    }

    function test_AllocateToStrategy_RevertsOnPerStrategyCap() public {
        // 60% of 100k = 60k cap
        vm.prank(operator);
        vm.expectRevert(AllocatorVault.MetaPerStrategyExceeded.selector);
        allocatorVault.allocateToStrategy(user, address(stratA), 60_001e6);
    }

    function test_AllocateToStrategy_RevertsOnUnregisteredStrategy() public {
        // Brand-new strategy never staked in registry.
        StrategyVault rogue = _deployStrategy(makeAddr("rogueOp"), CLASS_MOM);
        vm.prank(operator);
        vm.expectRevert(AllocatorVault.StrategyNotRegistered.selector);
        allocatorVault.allocateToStrategy(user, address(rogue), 1000e6);
    }

    function test_AllocateToStrategy_RevertsOnInactive() public {
        vm.prank(stratAOperator);
        registry.deactivate(address(stratA));
        vm.prank(operator);
        vm.expectRevert(AllocatorVault.StrategyInactive.selector);
        allocatorVault.allocateToStrategy(user, address(stratA), 1000e6);
    }

    function test_AllocateToStrategy_RevertsOnExpiredMeta() public {
        vm.warp(block.timestamp + 31 days);
        vm.prank(operator);
        vm.expectRevert(AllocatorVault.MetaExpired.selector);
        allocatorVault.allocateToStrategy(user, address(stratA), 1000e6);
    }

    function test_AllocateToStrategy_RevertsOnDisallowedClass() public {
        // Wipe meta classes.
        bytes32[] memory none = new bytes32[](1);
        none[0] = keccak256("yield_rotation_v1");
        userVault.setMeta(
            user,
            MetaStrategyLib.MetaStrategy({
                metaStrategyHash: bytes32(uint256(2)),
                allowedStrategyClasses: none,
                allowedAssets: new address[](0),
                allowedChains: new uint32[](0),
                maxCapital: USER_DEPOSIT,
                maxPerStrategyBps: 6000,
                maxStrategiesCount: 3,
                drawdownThresholdBps: DD_THRESHOLD_BPS,
                maxFeeRateBps: 2500,
                rebalanceCadenceSec: 0,
                validUntil: uint64(block.timestamp + 30 days)
            })
        );
        vm.prank(operator);
        vm.expectRevert(AllocatorVault.MetaClassNotAllowed.selector);
        allocatorVault.allocateToStrategy(user, address(stratA), 1000e6);
    }

    // ── defundStrategy ──────────────────────────────────────────────

    function test_DefundStrategy_RevertsOnNotAllocated() public {
        vm.prank(operator);
        vm.expectRevert(AllocatorVault.StrategyNotAllocated.selector);
        allocatorVault.defundStrategy(user, address(stratA), "noop");
    }

    function test_DefundStrategy_OperatorAnytime() public {
        vm.prank(operator);
        allocatorVault.allocateToStrategy(user, address(stratA), 30_000e6);

        vm.expectEmit(true, true, true, true);
        emit StrategyDefunded(user, address(stratA), "operator unwind", operator);
        vm.prank(operator);
        allocatorVault.defundStrategy(user, address(stratA), "operator unwind");

        IAllocatorVault.AllocationRecord memory r =
            allocatorVault.allocationOf(user, address(stratA));
        assertGt(r.defundedAt, 0);
        assertEq(r.capitalDeployed, 0);
        assertEq(userVault.balanceOf(user), USER_DEPOSIT);
    }

    function test_DefundStrategy_PermissionlessRevertsWhenDDNotBreached() public {
        vm.prank(operator);
        allocatorVault.allocateToStrategy(user, address(stratA), 30_000e6);
        vm.prank(randomCaller);
        vm.expectRevert(IAllocatorVault.DrawdownNotBreached.selector);
        allocatorVault.defundStrategy(user, address(stratA), "no DD");
    }

    function test_DefundStrategy_PermissionlessSucceedsOnBreach() public {
        vm.prank(operator);
        allocatorVault.allocateToStrategy(user, address(stratA), 30_000e6);

        // Simulate a 20% drawdown via signed NAV (15% threshold breached).
        _reportNAV(stratA, 24_000e6, uint64(block.timestamp + 1));

        vm.expectEmit(true, true, true, true);
        emit StrategyDefunded(user, address(stratA), "DD breach", randomCaller);
        vm.prank(randomCaller);
        allocatorVault.defundStrategy(user, address(stratA), "DD breach");

        IAllocatorVault.AllocationRecord memory r =
            allocatorVault.allocationOf(user, address(stratA));
        assertGt(r.defundedAt, 0);
    }

    function test_DefundStrategy_RevertsOnAlreadyDefunded() public {
        vm.prank(operator);
        allocatorVault.allocateToStrategy(user, address(stratA), 1000e6);
        vm.prank(operator);
        allocatorVault.defundStrategy(user, address(stratA), "first");
        vm.prank(operator);
        vm.expectRevert(AllocatorVault.AllocationDefunded.selector);
        allocatorVault.defundStrategy(user, address(stratA), "second");
    }

    // ── rebalance ──────────────────────────────────────────────────

    function test_Rebalance_OnlyOperator() public {
        address[] memory ss = new address[](1);
        uint256[] memory ws = new uint256[](1);
        ss[0] = address(stratA);
        ws[0] = 10_000;
        vm.prank(randomCaller);
        vm.expectRevert(IAllocatorVault.NotAllocator.selector);
        allocatorVault.rebalance(user, ss, ws);
    }

    function test_Rebalance_RevertsOnLengthMismatch() public {
        address[] memory ss = new address[](2);
        uint256[] memory ws = new uint256[](1);
        ss[0] = address(stratA);
        ss[1] = address(stratB);
        ws[0] = 10_000;
        vm.prank(operator);
        vm.expectRevert(AllocatorVault.LengthMismatch.selector);
        allocatorVault.rebalance(user, ss, ws);
    }

    function test_Rebalance_RevertsOnBadWeights() public {
        address[] memory ss = new address[](2);
        uint256[] memory ws = new uint256[](2);
        ss[0] = address(stratA);
        ss[1] = address(stratB);
        ws[0] = 5000;
        ws[1] = 6000; // sum 11_000
        vm.prank(operator);
        vm.expectRevert(AllocatorVault.InvalidWeights.selector);
        allocatorVault.rebalance(user, ss, ws);
    }

    function test_Rebalance_ShiftsCapitalBetweenStrategies() public {
        vm.prank(operator);
        allocatorVault.allocateToStrategy(user, address(stratA), 40_000e6);
        vm.prank(operator);
        allocatorVault.allocateToStrategy(user, address(stratB), 20_000e6);

        // Shift to 25/75 of 60k = 15k / 45k
        address[] memory ss = new address[](2);
        uint256[] memory ws = new uint256[](2);
        ss[0] = address(stratA);
        ss[1] = address(stratB);
        ws[0] = 2500;
        ws[1] = 7500;
        vm.prank(operator);
        allocatorVault.rebalance(user, ss, ws);

        assertEq(allocatorVault.allocationOf(user, address(stratA)).capitalDeployed, 15_000e6);
        assertEq(allocatorVault.allocationOf(user, address(stratB)).capitalDeployed, 45_000e6);
    }

    // ── settleStrategyFee ───────────────────────────────────────────

    function test_SettleStrategyFee_NoOpWhenUnderwater() public {
        vm.prank(operator);
        allocatorVault.allocateToStrategy(user, address(stratA), 10_000e6);
        vm.expectEmit(true, true, false, true);
        emit StrategyFeeSettled(user, address(stratA), 0, 10_000e6);
        allocatorVault.settleStrategyFee(user, address(stratA));
    }

    function test_SettleStrategyFee_SplitsRealizedThreeWays() public {
        vm.prank(operator);
        allocatorVault.allocateToStrategy(user, address(stratA), 10_000e6);
        // Simulate 1_000 USDC of realized gain: mint to strategy + report NAV.
        usdc.mint(address(stratA), 1000e6);
        _reportNAV(stratA, 11_000e6, uint64(block.timestamp + 1));

        uint256 stratOpBalBefore = usdc.balanceOf(stratAOperator);
        uint256 userBalBefore = userVault.balanceOf(user);
        uint256 accruedBefore = allocatorVault.accruedFees();

        allocatorVault.settleStrategyFee(user, address(stratA));

        // 1k realized: 10% strat fee = 100, 5% allocator fee = 50, user gets 850.
        assertEq(usdc.balanceOf(stratAOperator) - stratOpBalBefore, 100e6);
        assertEq(userVault.balanceOf(user) - userBalBefore, 850e6);
        assertEq(allocatorVault.accruedFees() - accruedBefore, 50e6);
        assertEq(allocatorVault.allocationOf(user, address(stratA)).strategyHighWaterMark, 11_000e6);
    }

    // ── withdrawAllocatorFees ───────────────────────────────────────

    function test_WithdrawAllocatorFees_RevertsOnZero() public {
        vm.prank(operator);
        vm.expectRevert(AllocatorVault.NoAccruedFees.selector);
        allocatorVault.withdrawAllocatorFees();
    }

    function test_WithdrawAllocatorFees_HappyPath() public {
        // Generate fees first.
        vm.prank(operator);
        allocatorVault.allocateToStrategy(user, address(stratA), 10_000e6);
        usdc.mint(address(stratA), 1000e6);
        _reportNAV(stratA, 11_000e6, uint64(block.timestamp + 1));
        allocatorVault.settleStrategyFee(user, address(stratA));

        uint256 opBefore = usdc.balanceOf(operator);
        vm.expectEmit(true, false, false, true);
        emit AllocatorFeesWithdrawn(operator, 50e6);
        vm.prank(operator);
        allocatorVault.withdrawAllocatorFees();
        assertEq(usdc.balanceOf(operator) - opBefore, 50e6);
        assertEq(allocatorVault.accruedFees(), 0);
    }

    // ── helpers ────────────────────────────────────────────────────

    function _reportNAV(StrategyVault s, uint256 nav, uint64 ts) internal {
        bytes32 digest = keccak256(abi.encode(block.chainid, address(s), nav, ts));
        (uint8 v, bytes32 r, bytes32 sigS) = vm.sign(navOracleKey, digest);
        bytes memory sig = abi.encodePacked(r, sigS, v);
        s.reportNAV(abi.encode(nav, ts, sig));
    }
}
