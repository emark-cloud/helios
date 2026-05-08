// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Test } from "forge-std/Test.sol";
import { ClassIds } from "../src/ClassIds.sol";
import { ReputationAnchor } from "../src/ReputationAnchor.sol";
import { StrategyRegistry } from "../src/StrategyRegistry.sol";
import { AllocatorRegistry } from "../src/AllocatorRegistry.sol";
import { IReputationAnchor } from "../src/interfaces/IReputationAnchor.sol";
import { IStrategyRegistry } from "../src/interfaces/IStrategyRegistry.sol";
import { IAllocatorRegistry } from "../src/interfaces/IAllocatorRegistry.sol";
import { MockERC20 } from "./mocks/MockERC20.sol";
import { Ownable } from "@openzeppelin/contracts/access/Ownable.sol";

contract ReputationAnchorTest is Test {
    ReputationAnchor internal anchor;
    StrategyRegistry internal sr;
    AllocatorRegistry internal ar;
    MockERC20 internal stake;

    address internal owner = makeAddr("owner");
    address internal oApp = makeAddr("oApp");

    uint256 internal signerPk = 0xA11CE;
    address internal signerAddr;

    address internal stratVault = makeAddr("stratVault");
    address internal allocVault = makeAddr("allocVault");
    address internal stratOperator = makeAddr("stratOperator");
    address internal allocOperator = makeAddr("allocOperator");

    bytes32 internal constant CLASS_MOMENTUM = ClassIds.MOMENTUM_V1;
    uint256 internal constant COOLDOWN = 7 days;
    uint256 internal constant STAKE = 10_000e18;

    function setUp() public {
        signerAddr = vm.addr(signerPk);
        stake = new MockERC20("Mock USDC", "mUSDC");

        anchor = new ReputationAnchor(signerAddr, oApp, owner);
        sr = new StrategyRegistry(stake, address(anchor), owner, COOLDOWN);
        ar = new AllocatorRegistry(stake, address(anchor), owner, COOLDOWN);

        vm.prank(owner);
        anchor.setRegistries(address(sr), address(ar));

        // Register a strategy + allocator so the registries have entries to update.
        stake.mint(stratOperator, 1_000_000e18);
        vm.prank(stratOperator);
        stake.approve(address(sr), type(uint256).max);
        vm.prank(stratOperator);
        sr.registerStrategy(stratVault, CLASS_MOMENTUM, STAKE);

        stake.mint(allocOperator, 1_000_000e18);
        vm.prank(allocOperator);
        stake.approve(address(ar), type(uint256).max);
        bytes32[] memory classes = new bytes32[](1);
        classes[0] = CLASS_MOMENTUM;
        vm.prank(allocOperator);
        ar.registerAllocator("Sigma", allocVault, bytes32(0), classes, 400, STAKE);
    }

    // ── Helpers ─────────────────────────────────────────────────────

    function _data(int256 score, uint256 lastBlock, IReputationAnchor.ActorType t)
        internal
        pure
        returns (IReputationAnchor.ReputationData memory)
    {
        return IReputationAnchor.ReputationData({
            currentScore: score,
            lastUpdateBlock: lastBlock,
            totalAttestedTrades: 5,
            totalRealizedPnL: 1000e18,
            maxDrawdownBps: 800,
            proofValidityRateBps: 9900,
            actorType: t,
            componentsHash: bytes32(0)
        });
    }

    function _sign(
        address actor,
        IReputationAnchor.ActorType t,
        IReputationAnchor.ReputationData memory d
    ) internal view returns (bytes memory) {
        bytes32 digest = anchor.hashUpdate(actor, t, d);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(signerPk, digest);
        return abi.encodePacked(r, s, v);
    }

    // ── Constructor + admin ─────────────────────────────────────────

    function test_Constructor_Wiring() public view {
        assertEq(anchor.reputationSigner(), signerAddr);
        assertEq(anchor.oApp(), oApp);
        assertEq(address(anchor.strategyRegistry()), address(sr));
        assertEq(address(anchor.allocatorRegistry()), address(ar));
        assertEq(anchor.owner(), owner);
    }

    function test_Constructor_RevertsOnZeroSigner() public {
        vm.expectRevert(ReputationAnchor.ZeroAddress.selector);
        new ReputationAnchor(address(0), oApp, owner);
    }

    function test_SetRegistries_OnlyOnce() public {
        // Already set in setUp.
        vm.prank(owner);
        vm.expectRevert(ReputationAnchor.RegistriesAlreadySet.selector);
        anchor.setRegistries(address(sr), address(ar));
    }

    function test_SetSigner_OnlyOwner() public {
        address newSigner = makeAddr("new");
        vm.prank(owner);
        anchor.setSigner(newSigner);
        assertEq(anchor.reputationSigner(), newSigner);

        vm.prank(makeAddr("rando"));
        vm.expectRevert();
        anchor.setSigner(newSigner);
    }

    function test_SetOApp_OnlyOwner() public {
        address newOApp = makeAddr("newOApp");
        vm.prank(owner);
        anchor.setOApp(newOApp);
        assertEq(anchor.oApp(), newOApp);
    }

    function test_Pause_BlocksPostUpdate() public {
        // MEDIUM in `docs/phase-3-review.md`: pause() must halt new
        // reputation posts so a compromised signer can't keep writing
        // while the team rotates keys.
        IReputationAnchor.ReputationData memory d =
            _data(750, block.number, IReputationAnchor.ActorType.STRATEGY);
        bytes memory sig = _sign(stratVault, IReputationAnchor.ActorType.STRATEGY, d);

        vm.prank(owner);
        anchor.pause();
        vm.expectRevert(); // EnforcedPause / Pausable revert
        anchor.postReputationUpdate(stratVault, IReputationAnchor.ActorType.STRATEGY, d, sig);

        vm.prank(owner);
        anchor.unpause();
        anchor.postReputationUpdate(stratVault, IReputationAnchor.ActorType.STRATEGY, d, sig);
        assertEq(anchor.reputationOf(stratVault).currentScore, 750);
    }

    function test_Pause_OnlyOwner() public {
        vm.prank(makeAddr("rando"));
        vm.expectRevert();
        anchor.pause();
    }

    // ── postReputationUpdate ────────────────────────────────────────

    function test_PostUpdate_Strategy_PushesToRegistry() public {
        IReputationAnchor.ReputationData memory d =
            _data(750, block.number, IReputationAnchor.ActorType.STRATEGY);
        bytes memory sig = _sign(stratVault, IReputationAnchor.ActorType.STRATEGY, d);

        vm.expectEmit(true, true, false, true);
        emit IReputationAnchor.ReputationPosted(
            stratVault, IReputationAnchor.ActorType.STRATEGY, 750, block.number
        );
        anchor.postReputationUpdate(stratVault, IReputationAnchor.ActorType.STRATEGY, d, sig);

        assertEq(anchor.reputationOf(stratVault).currentScore, 750);
        assertEq(sr.strategyOf(stratVault).currentReputation, 750);
    }

    function test_PostUpdate_Allocator_PushesToRegistry() public {
        IReputationAnchor.ReputationData memory d =
            _data(420, block.number, IReputationAnchor.ActorType.ALLOCATOR);
        bytes memory sig = _sign(allocVault, IReputationAnchor.ActorType.ALLOCATOR, d);

        anchor.postReputationUpdate(allocVault, IReputationAnchor.ActorType.ALLOCATOR, d, sig);

        assertEq(ar.allocatorOf(allocVault).currentReputation, 420);
    }

    function test_PostUpdate_DeltaIsAppliedAcrossUpdates() public {
        IReputationAnchor.ReputationData memory d1 =
            _data(500, block.number, IReputationAnchor.ActorType.STRATEGY);
        anchor.postReputationUpdate(
            stratVault,
            IReputationAnchor.ActorType.STRATEGY,
            d1,
            _sign(stratVault, IReputationAnchor.ActorType.STRATEGY, d1)
        );
        assertEq(sr.strategyOf(stratVault).currentReputation, 500);

        vm.roll(block.number + 1);
        IReputationAnchor.ReputationData memory d2 =
            _data(300, block.number, IReputationAnchor.ActorType.STRATEGY);
        anchor.postReputationUpdate(
            stratVault,
            IReputationAnchor.ActorType.STRATEGY,
            d2,
            _sign(stratVault, IReputationAnchor.ActorType.STRATEGY, d2)
        );
        assertEq(sr.strategyOf(stratVault).currentReputation, 300);
    }

    function test_PostUpdate_RevertsOnBadSignature() public {
        IReputationAnchor.ReputationData memory d =
            _data(100, block.number, IReputationAnchor.ActorType.STRATEGY);
        // Sign with a wrong key.
        uint256 wrongPk = 0xBEEF;
        bytes32 digest = anchor.hashUpdate(stratVault, IReputationAnchor.ActorType.STRATEGY, d);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(wrongPk, digest);
        bytes memory sig = abi.encodePacked(r, s, v);

        vm.expectRevert(IReputationAnchor.InvalidSigner.selector);
        anchor.postReputationUpdate(stratVault, IReputationAnchor.ActorType.STRATEGY, d, sig);
    }

    function test_PostUpdate_RejectsReplay() public {
        IReputationAnchor.ReputationData memory d =
            _data(100, block.number, IReputationAnchor.ActorType.STRATEGY);
        bytes memory sig = _sign(stratVault, IReputationAnchor.ActorType.STRATEGY, d);

        anchor.postReputationUpdate(stratVault, IReputationAnchor.ActorType.STRATEGY, d, sig);
        // Replaying the same payload at the same block reverts on monotonic check.
        vm.expectRevert(ReputationAnchor.StaleUpdate.selector);
        anchor.postReputationUpdate(stratVault, IReputationAnchor.ActorType.STRATEGY, d, sig);
    }

    function test_PostUpdate_RejectsLowerBlock() public {
        IReputationAnchor.ReputationData memory d1 =
            _data(100, 100, IReputationAnchor.ActorType.STRATEGY);
        anchor.postReputationUpdate(
            stratVault,
            IReputationAnchor.ActorType.STRATEGY,
            d1,
            _sign(stratVault, IReputationAnchor.ActorType.STRATEGY, d1)
        );

        IReputationAnchor.ReputationData memory d2 =
            _data(200, 50, IReputationAnchor.ActorType.STRATEGY);
        bytes memory sig = _sign(stratVault, IReputationAnchor.ActorType.STRATEGY, d2);

        vm.expectRevert(ReputationAnchor.StaleUpdate.selector);
        anchor.postReputationUpdate(stratVault, IReputationAnchor.ActorType.STRATEGY, d2, sig);
    }

    // ── postCrossChainUpdate ────────────────────────────────────────

    function test_PostCrossChain_OnlyOApp() public {
        IReputationAnchor.ReputationData memory d =
            _data(900, block.number, IReputationAnchor.ActorType.STRATEGY);

        vm.prank(makeAddr("notOApp"));
        vm.expectRevert(IReputationAnchor.NotOApp.selector);
        anchor.postCrossChainUpdate(stratVault, IReputationAnchor.ActorType.STRATEGY, d);

        vm.prank(oApp);
        anchor.postCrossChainUpdate(stratVault, IReputationAnchor.ActorType.STRATEGY, d);
        assertEq(anchor.reputationOf(stratVault).currentScore, 900);
        assertEq(sr.strategyOf(stratVault).currentReputation, 900);
    }

    // ── postCrossChainTradeTick (Phase-5 review H3, H4) ─────────────

    function test_TradeTick_OnlyOApp() public {
        vm.prank(makeAddr("notOApp"));
        vm.expectRevert(IReputationAnchor.NotOApp.selector);
        anchor.postCrossChainTradeTick(stratVault);
    }

    function test_TradeTick_IncrementsCounterOnly() public {
        // Seed a real engine score on Kite so we can prove the tick does
        // not clobber it (H3 canary).
        IReputationAnchor.ReputationData memory seed =
            _data(750, block.number, IReputationAnchor.ActorType.STRATEGY);
        anchor.postReputationUpdate(
            stratVault,
            IReputationAnchor.ActorType.STRATEGY,
            seed,
            _sign(stratVault, IReputationAnchor.ActorType.STRATEGY, seed)
        );
        IReputationAnchor.ReputationData memory before = anchor.reputationOf(stratVault);

        vm.prank(oApp);
        anchor.postCrossChainTradeTick(stratVault);

        IReputationAnchor.ReputationData memory aft = anchor.reputationOf(stratVault);
        assertEq(aft.currentScore, before.currentScore, "score must not change");
        assertEq(aft.totalRealizedPnL, before.totalRealizedPnL, "pnl must not change");
        assertEq(aft.maxDrawdownBps, before.maxDrawdownBps, "drawdown must not change");
        assertEq(
            aft.proofValidityRateBps,
            before.proofValidityRateBps,
            "validity rate must not change"
        );
        assertEq(aft.lastUpdateBlock, before.lastUpdateBlock, "lastUpdateBlock must not change");
        assertEq(aft.totalAttestedTrades, before.totalAttestedTrades + 1, "trade count +1");
        // Registry score also must not be touched — no delta propagated.
        assertEq(sr.strategyOf(stratVault).currentReputation, 750, "registry score untouched");
    }

    function test_TradeTick_DoesNotDoSEngineUpdates() public {
        // H4 canary: a tick must not freeze the engine's freshness check.
        // Pre-fix, the OApp wrote `lastUpdateBlock = remote block.number`
        // which (e.g. an Arb sequencer block ~190M) prevented every
        // subsequent engine `postReputationUpdate` from passing
        // `data.lastUpdateBlock > prev.lastUpdateBlock`.
        IReputationAnchor.ReputationData memory seed =
            _data(500, block.number, IReputationAnchor.ActorType.STRATEGY);
        anchor.postReputationUpdate(
            stratVault,
            IReputationAnchor.ActorType.STRATEGY,
            seed,
            _sign(stratVault, IReputationAnchor.ActorType.STRATEGY, seed)
        );

        vm.prank(oApp);
        anchor.postCrossChainTradeTick(stratVault);

        // Roll forward and let the engine post its next score normally.
        vm.roll(block.number + 1);
        IReputationAnchor.ReputationData memory next =
            _data(620, block.number, IReputationAnchor.ActorType.STRATEGY);
        bytes memory sig = _sign(stratVault, IReputationAnchor.ActorType.STRATEGY, next);
        anchor.postReputationUpdate(stratVault, IReputationAnchor.ActorType.STRATEGY, next, sig);
        assertEq(anchor.reputationOf(stratVault).currentScore, 620, "engine update must apply");
    }

    function test_TradeTick_FromZeroState_DoesNotCrashRegistry() public {
        // No prior state for stratVault. Tick must succeed and not push a
        // registry delta (no propagation), so the registry's
        // `currentReputation` stays at 0.
        vm.prank(oApp);
        anchor.postCrossChainTradeTick(stratVault);
        assertEq(anchor.reputationOf(stratVault).totalAttestedTrades, 1);
        assertEq(sr.strategyOf(stratVault).currentReputation, 0, "no registry delta");
    }
}
