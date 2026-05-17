// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Test } from "forge-std/Test.sol";
import { ClassIds } from "../src/ClassIds.sol";
import { AllocatorVault } from "../src/AllocatorVault.sol";
import { IAllocatorVault } from "../src/interfaces/IAllocatorVault.sol";
import { StrategyVault } from "../src/StrategyVault.sol";
import { IStrategyVault } from "../src/interfaces/IStrategyVault.sol";
import { StrategyRegistry } from "../src/StrategyRegistry.sol";
import { TradeAttestationVerifier } from "../src/TradeAttestationVerifier.sol";
import { MockERC20 } from "./mocks/MockERC20.sol";
import { MockGroth16Verifier } from "./mocks/MockGroth16Verifier.sol";
import { MockOracleAnchor } from "./mocks/MockOracleAnchor.sol";
import { MockUserVault } from "./mocks/MockUserVault.sol";
import { MockSwapRouter } from "./mocks/MockSwapRouter.sol";
import { MetaStrategyLib } from "../src/interfaces/IMetaStrategy.sol";
import { ERC1967Proxy } from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";
import {
    PausableUpgradeable
} from "@openzeppelin/contracts-upgradeable/utils/PausableUpgradeable.sol";

/// @notice Coverage for the privileged proof-less defund-unwind
///         (`StrategyVault.unwindToBase`) and its
///         `AllocatorVault._unwindAndCredit` hook. Self-contained stack
///         with a REAL `MockSwapRouter` + a multi-asset universe so the
///         swap path is exercised — the shared `AllocatorVault.t.sol`
///         harness uses a stub router + `[usdc]` universe and must not
///         be perturbed.
contract StrategyVaultUnwindTest is Test {
    AllocatorVault internal allocatorVault;
    StrategyRegistry internal registry;
    TradeAttestationVerifier internal verifier;
    MockGroth16Verifier internal classVerifier;
    MockERC20 internal usdc;
    MockERC20 internal wbtc;
    MockERC20 internal sol;
    MockUserVault internal userVault;
    MockOracleAnchor internal oracleAnchor;
    MockSwapRouter internal router;

    address internal owner = makeAddr("owner");
    address internal operator = makeAddr("operator");
    address internal stratOp = makeAddr("stratOp");
    address internal navOracle;
    uint256 internal navOracleKey;
    address internal priceAnchor = makeAddr("priceAnchor");
    address internal yieldAnchor = makeAddr("yieldAnchor");
    address internal user = makeAddr("user");
    address internal rando = makeAddr("rando");
    address internal sink = makeAddr("sink");

    bytes32 internal constant CLASS_MR = ClassIds.MEAN_REVERSION_V1;
    uint16 internal constant ALLOCATOR_FEE_BPS = 500;
    uint16 internal constant STRAT_FEE_BPS = 1000;
    uint16 internal constant DD_THRESHOLD_BPS = 1500;
    uint256 internal constant USER_DEPOSIT = 1_000_000e18;

    // Unit-mode vault whose `allocatorVault` is an EOA we can prank
    // directly into `unwindToBase` without the full AllocatorVault.
    address internal avEOA = makeAddr("avEOA");

    event AssetUnwound(
        address indexed strategy, address indexed asset, uint256 amountIn, uint256 baseReceived
    );
    event UnwoundToBase(
        address indexed strategy,
        uint256 totalBaseReceived,
        uint256 nonBaseMarkedValue,
        uint256 assetsSwept
    );

    function setUp() public {
        (navOracle, navOracleKey) = makeAddrAndKey("navOracle");
        usdc = new MockERC20("USDC", "USDC");
        wbtc = new MockERC20("WBTC", "WBTC");
        sol = new MockERC20("SOL", "SOL");
        userVault = new MockUserVault(usdc);

        address reputationAnchor = makeAddr("repAnchor");
        registry = new StrategyRegistry(usdc, reputationAnchor, owner, 7 days);
        verifier = new TradeAttestationVerifier(owner);
        classVerifier = new MockGroth16Verifier(true);
        vm.prank(owner);
        verifier.registerVerifier(CLASS_MR, address(classVerifier));

        // Real swap router seeded with deep usdc inventory + fair
        // 1:1 prices (mock ignores decimals — pure num/denom ratio).
        router = new MockSwapRouter(owner);
        usdc.mint(address(router), 100_000_000e18);
        vm.startPrank(owner);
        router.setPrice(address(wbtc), address(usdc), 1, 1);
        router.setPrice(address(sol), address(usdc), 1, 1);
        vm.stopPrank();

        AllocatorVault avImpl = new AllocatorVault();
        bytes memory avInit = abi.encodeCall(
            AllocatorVault.initialize,
            (usdc, operator, address(userVault), address(registry), ALLOCATOR_FEE_BPS, owner)
        );
        allocatorVault = AllocatorVault(address(new ERC1967Proxy(address(avImpl), avInit)));

        oracleAnchor = new MockOracleAnchor();
        oracleAnchor.setLatest(uint64(block.timestamp));
        vm.prank(owner);
        allocatorVault.setOracleAnchor(address(oracleAnchor));
    }

    // ── helpers ─────────────────────────────────────────────────────

    function _universe() internal view returns (address[] memory u) {
        u = new address[](3);
        u[0] = address(usdc);
        u[1] = address(wbtc);
        u[2] = address(sol);
    }

    function _deployStrategy(address allocator) internal returns (StrategyVault s) {
        StrategyVault impl = new StrategyVault(priceAnchor, yieldAnchor);
        IStrategyVault.StrategyManifest memory m = IStrategyVault.StrategyManifest({
            declaredClass: CLASS_MR,
            assetUniverse: _universe(),
            maxCapacity: 100_000_000e18,
            feeRateBps: STRAT_FEE_BPS,
            operator: stratOp,
            stakeAmount: 5000e18,
            paramsHash: bytes32(0)
        });
        StrategyVault.InitParams memory p = StrategyVault.InitParams({
            manifest: m,
            baseAsset: usdc,
            registry: address(registry),
            verifier: address(verifier),
            allowedRouter: address(router),
            navOracle: navOracle,
            allocatorVault: allocator,
            priceAnchor: priceAnchor,
            yieldAnchor: yieldAnchor,
            owner: owner
        });
        bytes memory initData = abi.encodeCall(StrategyVault.initialize, (p));
        s = StrategyVault(address(new ERC1967Proxy(address(impl), initData)));
    }

    function _reportNAV(StrategyVault s, uint256 nav, uint64 ts) internal {
        bytes32 digest = s.navDigest(nav, ts);
        (uint8 v, bytes32 r, bytes32 sigS) = vm.sign(navOracleKey, digest);
        vm.prank(s.manifest().operator);
        s.reportNAV(abi.encode(nav, ts, abi.encodePacked(r, sigS, v)));
    }

    /// @dev Put `s` into the live-bug shape: principal allocated, then
    ///      cash rotated into wbtc/sol positions while reportNAV keeps
    ///      the aggregate mark, so liquid base ≪ NAV (the 0x1717640c
    ///      condition).
    function _putInPosition(StrategyVault s, uint256 principal, uint256 cashLeft) internal {
        usdc.mint(avEOA, principal);
        vm.prank(avEOA);
        usdc.approve(address(s), principal);
        vm.prank(avEOA);
        s.allocateFrom(principal); // vault usdc = principal, _totalNAV = principal

        uint256 inPositions = principal - cashLeft;
        // Rotate `inPositions` of base out, split equally into wbtc+sol
        // (1:1 router price → each worth inPositions/2 base).
        vm.prank(address(s));
        usdc.transfer(sink, inPositions);
        wbtc.mint(address(s), inPositions / 2);
        sol.mint(address(s), inPositions / 2);
        // NAV still marks the full principal (cash + position value).
        _reportNAV(s, principal, uint64(block.timestamp + 1));
    }

    // ── unit: unwindToBase ──────────────────────────────────────────

    function test_UnwindToBase_SwapsAllNonBaseToBase() public {
        StrategyVault s = _deployStrategy(avEOA);
        _putInPosition(s, 1000e18, 300e18); // 700 in wbtc+sol
        uint256 navBefore = s.totalNAV();

        vm.expectEmit(true, true, false, false);
        emit AssetUnwound(address(s), address(wbtc), 350e18, 0);
        vm.prank(avEOA);
        s.unwindToBase();

        assertEq(wbtc.balanceOf(address(s)), 0, "wbtc swept");
        assertEq(sol.balanceOf(address(s)), 0, "sol swept");
        // 300 cash + 700 recovered (1:1) = ~1000 base now liquid.
        assertEq(usdc.balanceOf(address(s)), 1000e18, "base restored");
        assertEq(s.totalNAV(), navBefore, "NAV unchanged by unwind");
    }

    function test_UnwindToBase_NoOpWhenFlat() public {
        StrategyVault s = _deployStrategy(avEOA);
        usdc.mint(avEOA, 500e18);
        vm.prank(avEOA);
        usdc.approve(address(s), 500e18);
        vm.prank(avEOA);
        s.allocateFrom(500e18);
        _reportNAV(s, 500e18, uint64(block.timestamp + 1));

        vm.prank(avEOA);
        s.unwindToBase(); // no non-base balances → true no-op

        assertEq(usdc.balanceOf(address(s)), 500e18);
    }

    function test_UnwindToBase_NoOpWhenFlatButNavAboveCash() public {
        // Regression: a base-only-holding vault that reported a GAIN
        // (NAV > cash, no positions) must NOT trip the slippage floor.
        StrategyVault s = _deployStrategy(avEOA);
        usdc.mint(avEOA, 500e18);
        vm.prank(avEOA);
        usdc.approve(address(s), 500e18);
        vm.prank(avEOA);
        s.allocateFrom(500e18);
        _reportNAV(s, 800e18, uint64(block.timestamp + 1)); // marked gain, no position

        vm.prank(avEOA);
        s.unwindToBase(); // swept==0 → floor skipped → no revert

        assertEq(usdc.balanceOf(address(s)), 500e18);
    }

    function test_UnwindToBase_DustZeroBalanceSkipped() public {
        StrategyVault s = _deployStrategy(avEOA);
        usdc.mint(avEOA, 1000e18);
        vm.prank(avEOA);
        usdc.approve(address(s), 1000e18);
        vm.prank(avEOA);
        s.allocateFrom(1000e18);
        vm.prank(address(s));
        usdc.transfer(sink, 400e18);
        wbtc.mint(address(s), 400e18); // only wbtc held; sol = 0
        _reportNAV(s, 1000e18, uint64(block.timestamp + 1));

        vm.expectEmit(true, false, false, false);
        emit UnwoundToBase(address(s), 0, 0, 1); // exactly one asset swept
        vm.prank(avEOA);
        s.unwindToBase();

        assertEq(wbtc.balanceOf(address(s)), 0);
        assertEq(usdc.balanceOf(address(s)), 1000e18);
    }

    function test_UnwindToBase_SlippageGuardReverts() public {
        StrategyVault s = _deployStrategy(avEOA);
        _putInPosition(s, 1000e18, 300e18); // 700 marked in positions
        // Router pays only 0.5 base per asset unit → recovers 350,
        // floor = 700 * 0.95 = 665 → revert.
        vm.startPrank(owner);
        router.setPrice(address(wbtc), address(usdc), 1, 2);
        router.setPrice(address(sol), address(usdc), 1, 2);
        vm.stopPrank();

        vm.prank(avEOA);
        vm.expectRevert(
            abi.encodeWithSelector(IStrategyVault.UnwindSlippageExceeded.selector, 350e18, 665e18)
        );
        s.unwindToBase();
    }

    function test_UnwindToBase_RouterRevertBubblesAsTradeCallFailed() public {
        StrategyVault s = _deployStrategy(avEOA);
        _putInPosition(s, 1000e18, 300e18);
        // Force a router revert by draining its usdc inventory so the
        // first swap reverts InsufficientLiquidity inside the call.
        // NB: read the balance into a local FIRST — `vm.prank` only
        // applies to the next call, and `balanceOf(...)` as an argument
        // is itself a call that would consume the prank.
        uint256 routerBal = usdc.balanceOf(address(router));
        vm.prank(address(router));
        usdc.transfer(sink, routerBal);

        vm.prank(avEOA);
        vm.expectRevert(abi.encodeWithSelector(StrategyVault.TradeCallFailed.selector, 0));
        s.unwindToBase();
    }

    function test_UnwindToBase_OnlyAllocatorVaultGate() public {
        StrategyVault s = _deployStrategy(avEOA);
        _putInPosition(s, 1000e18, 300e18);

        vm.prank(rando);
        vm.expectRevert(StrategyVault.NotAllocatorVault.selector);
        s.unwindToBase();

        vm.prank(owner);
        vm.expectRevert(StrategyVault.NotAllocatorVault.selector);
        s.unwindToBase();

        vm.prank(stratOp);
        vm.expectRevert(StrategyVault.NotAllocatorVault.selector);
        s.unwindToBase();
    }

    function test_UnwindToBase_WorksWhenPaused() public {
        StrategyVault s = _deployStrategy(avEOA);
        _putInPosition(s, 1000e18, 300e18);
        vm.prank(owner);
        s.pause();

        vm.prank(avEOA);
        s.unwindToBase(); // defund path must work even when paused

        assertEq(wbtc.balanceOf(address(s)), 0);
        assertEq(usdc.balanceOf(address(s)), 1000e18);
    }

    // ── integration: AllocatorVault defund of an in-position vault ──

    function _wireUserAndStrategy() internal returns (StrategyVault s) {
        s = _deployStrategy(address(allocatorVault));
        usdc.mint(stratOp, 5000e18);
        vm.startPrank(stratOp);
        usdc.approve(address(registry), type(uint256).max);
        registry.registerStrategy(address(s), CLASS_MR, 5000e18);
        vm.stopPrank();

        bytes32[] memory classes = new bytes32[](1);
        classes[0] = CLASS_MR;
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
                maxPerStrategyBps: 10_000,
                maxStrategiesCount: 3,
                drawdownThresholdBps: DD_THRESHOLD_BPS,
                maxFeeRateBps: 2500,
                rebalanceCadenceSec: 1 days,
                validUntil: uint64(block.timestamp + 30 days),
                defundTwapBars: MetaStrategyLib.DEFAULT_DEFUND_TWAP_BARS,
                defundBondBps: MetaStrategyLib.DEFAULT_DEFUND_BOND_BPS,
                defundConfirmBlocks: MetaStrategyLib.DEFAULT_DEFUND_CONFIRM_BLOCKS
            })
        );
        userVault.setAllocator(user, address(allocatorVault));
        usdc.mint(address(this), USER_DEPOSIT);
        usdc.approve(address(userVault), USER_DEPOSIT);
        userVault.deposit(user, USER_DEPOSIT);
    }

    /// @dev Drive the strategy into the live-bug shape THROUGH the
    ///      AllocatorVault (so allocationOf/_totalNAV bookkeeping is
    ///      real), then verify defund no longer reverts
    ///      ERC20InsufficientBalance.
    function test_DefundStrategy_InPositionVault_SucceedsEndToEnd() public {
        StrategyVault s = _wireUserAndStrategy();
        vm.prank(operator);
        allocatorVault.allocateToStrategy(user, address(s), 1000e18);

        // Rotate 700 base into wbtc/sol positions; NAV stays marked.
        vm.prank(address(s));
        usdc.transfer(sink, 700e18);
        wbtc.mint(address(s), 350e18);
        sol.mint(address(s), 350e18);
        _reportNAV(s, 1000e18, uint64(block.timestamp + 1));
        assertLt(usdc.balanceOf(address(s)), s.navOf(address(allocatorVault)), "bug shape staged");

        uint256 userBefore = userVault.balanceOf(user);
        vm.prank(operator);
        allocatorVault.defundStrategy(user, address(s), "RANK_DROP"); // no 0xe450d38c

        assertEq(wbtc.balanceOf(address(s)), 0, "wbtc unwound");
        assertEq(sol.balanceOf(address(s)), 0, "sol unwound");
        assertEq(userVault.balanceOf(user) - userBefore, 1000e18, "user fully credited");
        assertEq(
            allocatorVault.allocationOf(user, address(s)).capitalDeployed, 0, "position closed"
        );
    }

    function test_FinalizeDefund_InPositionVault_SucceedsEndToEnd() public {
        StrategyVault s = _wireUserAndStrategy();
        vm.prank(operator);
        allocatorVault.allocateToStrategy(user, address(s), 1000e18);

        // Position + a single >15% drawdown mark (20% DD vs 1000
        // principal). The mark persists across triggers — no per-bar
        // re-report — mirroring the proven `_armPendingDefund` cadence.
        vm.prank(address(s));
        usdc.transfer(sink, 700e18);
        wbtc.mint(address(s), 350e18);
        sol.mint(address(s), 350e18);
        _reportNAV(s, 800e18, uint64(block.timestamp + 1));

        usdc.mint(address(this), 10_000e18);
        usdc.approve(address(allocatorVault), type(uint256).max);

        allocatorVault.triggerDefund(user, address(s)); // breach 1
        uint256 target = block.number;
        for (uint256 i = 0; i < MetaStrategyLib.DEFAULT_DEFUND_TWAP_BARS - 1; i++) {
            target += 300; // == MIN_BAR_BLOCKS
            vm.roll(target);
            oracleAnchor.setLatest(uint64(block.timestamp));
            allocatorVault.triggerDefund(user, address(s)); // breach 2,3 → armed
        }
        vm.roll(block.number + 26); // > defundConfirmBlocks (25)

        uint256 userBefore = userVault.balanceOf(user);
        allocatorVault.finalizeDefund(user, address(s)); // permissionless, no 0xe450d38c

        assertEq(wbtc.balanceOf(address(s)), 0);
        assertEq(sol.balanceOf(address(s)), 0);
        assertGt(userVault.balanceOf(user) - userBefore, 0, "user credited NAV share");
        assertEq(allocatorVault.allocationOf(user, address(s)).capitalDeployed, 0);
    }

    function test_DefundStrategy_FlatVault_StillSucceeds() public {
        StrategyVault s = _wireUserAndStrategy();
        vm.prank(operator);
        allocatorVault.allocateToStrategy(user, address(s), 1000e18);
        _reportNAV(s, 1000e18, uint64(block.timestamp + 1)); // no positions

        uint256 userBefore = userVault.balanceOf(user);
        vm.prank(operator);
        allocatorVault.defundStrategy(user, address(s), "RANK_DROP");

        assertEq(userVault.balanceOf(user) - userBefore, 1000e18);
        assertEq(allocatorVault.allocationOf(user, address(s)).capitalDeployed, 0);
    }
}
