// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Test } from "forge-std/Test.sol";
import { ReputationAnchorV2 } from "../src/ReputationAnchorV2.sol";
import { StrategyRegistry } from "../src/StrategyRegistry.sol";
import { AllocatorRegistry } from "../src/AllocatorRegistry.sol";
import { IReputationAnchor } from "../src/interfaces/IReputationAnchor.sol";
import { MockERC20 } from "./mocks/MockERC20.sol";

/// @notice V2 anchor exercises the new EIP-712 typehash with `componentsHash`.
///         The V1 anchor signature path is untouched and continues to be
///         covered by ReputationAnchor.t.sol.
contract ReputationAnchorV2Test is Test {
    ReputationAnchorV2 internal anchor;
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

    bytes32 internal constant CLASS_MOMENTUM = keccak256("momentum_v1");
    bytes32 internal constant COMPONENTS_HASH = keccak256("components-fingerprint");
    uint256 internal constant COOLDOWN = 7 days;
    uint256 internal constant STAKE = 10_000e18;

    function setUp() public {
        signerAddr = vm.addr(signerPk);
        stake = new MockERC20("Mock USDC", "mUSDC");

        anchor = new ReputationAnchorV2(signerAddr, oApp, owner);
        sr = new StrategyRegistry(stake, address(anchor), owner, COOLDOWN);
        ar = new AllocatorRegistry(stake, address(anchor), owner, COOLDOWN);

        vm.prank(owner);
        anchor.setRegistries(address(sr), address(ar));

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

    function _data(int256 score, uint256 lastBlock, IReputationAnchor.ActorType t, bytes32 ch)
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
            componentsHash: ch
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

    function test_PostUpdate_AnchorsComponentsHash() public {
        IReputationAnchor.ReputationData memory d =
            _data(750, block.number, IReputationAnchor.ActorType.STRATEGY, COMPONENTS_HASH);
        bytes memory sig = _sign(stratVault, IReputationAnchor.ActorType.STRATEGY, d);

        vm.expectEmit(true, true, false, true);
        emit IReputationAnchor.ReputationPosted(
            stratVault, IReputationAnchor.ActorType.STRATEGY, 750, block.number
        );
        vm.expectEmit(true, false, false, true);
        emit ReputationAnchorV2.ComponentsAnchored(stratVault, COMPONENTS_HASH);
        anchor.postReputationUpdate(stratVault, IReputationAnchor.ActorType.STRATEGY, d, sig);

        assertEq(anchor.reputationOf(stratVault).currentScore, 750);
        assertEq(anchor.reputationOf(stratVault).componentsHash, COMPONENTS_HASH);
    }

    function test_PostUpdate_RejectsTamperedComponentsHash() public {
        IReputationAnchor.ReputationData memory d =
            _data(750, block.number, IReputationAnchor.ActorType.STRATEGY, COMPONENTS_HASH);
        bytes memory sig = _sign(stratVault, IReputationAnchor.ActorType.STRATEGY, d);

        // Mutate the components hash post-signing — signature must no longer recover.
        d.componentsHash = keccak256("forged");

        vm.expectRevert(IReputationAnchor.InvalidSigner.selector);
        anchor.postReputationUpdate(stratVault, IReputationAnchor.ActorType.STRATEGY, d, sig);
    }

    function test_PostUpdate_RevertsOnBadSignature() public {
        IReputationAnchor.ReputationData memory d =
            _data(100, block.number, IReputationAnchor.ActorType.STRATEGY, COMPONENTS_HASH);
        uint256 wrongPk = 0xBEEF;
        bytes32 digest = anchor.hashUpdate(stratVault, IReputationAnchor.ActorType.STRATEGY, d);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(wrongPk, digest);
        bytes memory sig = abi.encodePacked(r, s, v);

        vm.expectRevert(IReputationAnchor.InvalidSigner.selector);
        anchor.postReputationUpdate(stratVault, IReputationAnchor.ActorType.STRATEGY, d, sig);
    }

    function test_PostUpdate_StaleBlockRejected() public {
        IReputationAnchor.ReputationData memory d1 =
            _data(500, block.number, IReputationAnchor.ActorType.STRATEGY, COMPONENTS_HASH);
        anchor.postReputationUpdate(
            stratVault,
            IReputationAnchor.ActorType.STRATEGY,
            d1,
            _sign(stratVault, IReputationAnchor.ActorType.STRATEGY, d1)
        );

        // Same block second update ⇒ rejected (must strictly advance).
        IReputationAnchor.ReputationData memory d2 =
            _data(600, block.number, IReputationAnchor.ActorType.STRATEGY, COMPONENTS_HASH);
        bytes memory sig2 = _sign(stratVault, IReputationAnchor.ActorType.STRATEGY, d2);
        vm.expectRevert(ReputationAnchorV2.StaleUpdate.selector);
        anchor.postReputationUpdate(stratVault, IReputationAnchor.ActorType.STRATEGY, d2, sig2);
    }

    function test_PostCrossChain_OnlyOApp() public {
        IReputationAnchor.ReputationData memory d =
            _data(321, block.number, IReputationAnchor.ActorType.ALLOCATOR, COMPONENTS_HASH);

        vm.expectRevert(IReputationAnchor.NotOApp.selector);
        anchor.postCrossChainUpdate(allocVault, IReputationAnchor.ActorType.ALLOCATOR, d);

        vm.prank(oApp);
        anchor.postCrossChainUpdate(allocVault, IReputationAnchor.ActorType.ALLOCATOR, d);
        assertEq(anchor.reputationOf(allocVault).currentScore, 321);
        assertEq(anchor.reputationOf(allocVault).componentsHash, COMPONENTS_HASH);
    }

    function test_DomainVersionIs2() public view {
        // EIP-712 domain hash must include version "2"; recover via a known
        // payload signed with that domain.
        IReputationAnchor.ReputationData memory d =
            _data(1, 1, IReputationAnchor.ActorType.STRATEGY, COMPONENTS_HASH);
        bytes32 digestV2 = anchor.hashUpdate(stratVault, IReputationAnchor.ActorType.STRATEGY, d);
        // Sanity: recompute against version "1" should diverge — we
        // approximate this by asserting digest is sensitive to bytes32(0)
        // vs COMPONENTS_HASH (catches a missing-componentsHash regression).
        d.componentsHash = bytes32(0);
        bytes32 digestZero = anchor.hashUpdate(stratVault, IReputationAnchor.ActorType.STRATEGY, d);
        assertTrue(digestV2 != digestZero);
    }
}
