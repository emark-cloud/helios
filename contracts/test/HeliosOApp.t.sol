// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Test } from "forge-std/Test.sol";

import { HeliosOApp } from "../src/HeliosOApp.sol";
import { CrossChainCodec } from "../src/lib/CrossChainCodec.sol";
import { IHeliosOApp } from "../src/interfaces/IHeliosOApp.sol";
import { IReputationAnchor } from "../src/interfaces/IReputationAnchor.sol";

import { MockLzEndpoint } from "./mocks/MockLzEndpoint.sol";
import { MockReputationAnchor } from "./mocks/MockReputationAnchor.sol";

contract HeliosOAppTest is Test {
    uint32 internal constant KITE_EID = 30_001;
    uint32 internal constant BASE_EID = 40_245;

    MockLzEndpoint internal kiteEndpoint;
    MockLzEndpoint internal baseEndpoint;
    MockReputationAnchor internal anchor;
    HeliosOApp internal kiteOApp;
    HeliosOApp internal baseOApp;

    address internal owner = address(0xA11CE);
    address internal strategyVault = address(0xB0B);
    address internal strategy = address(0xCAFE);

    function setUp() public {
        kiteEndpoint = new MockLzEndpoint(KITE_EID);
        baseEndpoint = new MockLzEndpoint(BASE_EID);
        kiteEndpoint.setPeer(baseEndpoint);
        baseEndpoint.setPeer(kiteEndpoint);

        anchor = new MockReputationAnchor();

        vm.prank(owner);
        kiteOApp = new HeliosOApp(address(kiteEndpoint), owner, KITE_EID, address(anchor), 64);

        vm.prank(owner);
        baseOApp = new HeliosOApp(address(baseEndpoint), owner, KITE_EID, address(0), 64);

        anchor.setOApp(address(kiteOApp));

        vm.prank(owner);
        kiteOApp.setPeer(BASE_EID, _addrToBytes32(address(baseOApp)));
        vm.prank(owner);
        baseOApp.setPeer(KITE_EID, _addrToBytes32(address(kiteOApp)));

        vm.prank(owner);
        baseOApp.setStrategyVault(strategyVault, true);
        // `strategy` is also allowlisted as a vault so that single-update
        // tests, where the vault is itself the actor, can exercise
        // `sendReputationUpdate(actor=msg.sender)`. See C1 gate.
        vm.prank(owner);
        baseOApp.setStrategyVault(strategy, true);
    }

    // ── Codec round-trip ───────────────────────────────────────────

    function test_codec_singleReputationRoundTrip() public view {
        IReputationAnchor.ReputationData memory data = _sampleData(123);
        CrossChainCodec.ReputationUpdateV1 memory update = CrossChainCodec.ReputationUpdateV1({
            seq: 7,
            actor: address(0xCAFE),
            actorType: IReputationAnchor.ActorType.STRATEGY,
            data: data
        });
        bytes memory encoded = CrossChainCodec.encodeReputationUpdate(update);
        CrossChainCodec.ReputationUpdateV1 memory got = this.decodeRep(encoded);
        assertEq(got.seq, update.seq, "seq");
        assertEq(got.actor, update.actor, "actor");
        assertEq(uint8(got.actorType), uint8(update.actorType), "actorType");
        assertEq(got.data.currentScore, data.currentScore, "score");
    }

    function test_codec_batchRoundTrip() public view {
        CrossChainCodec.ReputationBatchEntry[] memory entries =
            new CrossChainCodec.ReputationBatchEntry[](2);
        entries[0] = CrossChainCodec.ReputationBatchEntry({
            seq: 1, strategy: address(0x1), data: _sampleData(10)
        });
        entries[1] = CrossChainCodec.ReputationBatchEntry({
            seq: 2, strategy: address(0x2), data: _sampleData(20)
        });
        bytes memory encoded = CrossChainCodec.encodeReputationBatch(entries);
        CrossChainCodec.ReputationBatchEntry[] memory got = this.decodeBatch(encoded);
        assertEq(got.length, 2, "len");
        assertEq(got[0].seq, 1, "seq0");
        assertEq(got[1].strategy, address(0x2), "strategy1");
    }

    function test_codec_bridgeRoundTrip() public view {
        CrossChainCodec.BridgeDeployV1 memory body = CrossChainCodec.BridgeDeployV1({
            seq: 9, strategy: address(0xCAFE), amount: 1_000_000
        });
        bytes memory encoded = CrossChainCodec.encodeBridgeDeploy(body);
        CrossChainCodec.BridgeDeployV1 memory got = this.decodeBridge(encoded);
        assertEq(got.seq, body.seq);
        assertEq(got.strategy, body.strategy);
        assertEq(got.amount, body.amount);
    }

    function decodeRep(bytes calldata encoded)
        external
        pure
        returns (CrossChainCodec.ReputationUpdateV1 memory)
    {
        return CrossChainCodec.decodeReputationUpdate(encoded);
    }

    function decodeBatch(bytes calldata encoded)
        external
        pure
        returns (CrossChainCodec.ReputationBatchEntry[] memory)
    {
        return CrossChainCodec.decodeReputationBatch(encoded);
    }

    function decodeBridge(bytes calldata encoded)
        external
        pure
        returns (CrossChainCodec.BridgeDeployV1 memory)
    {
        return CrossChainCodec.decodeBridgeDeploy(encoded);
    }

    function test_codec_kindMismatchReverts() public {
        CrossChainCodec.BridgeDeployV1 memory body =
            CrossChainCodec.BridgeDeployV1({ seq: 1, strategy: strategy, amount: 1 });
        bytes memory encoded = CrossChainCodec.encodeBridgeDeploy(body);
        vm.expectRevert();
        this._decodeAsReputation(encoded);
    }

    // ── Send → deliver → anchor ───────────────────────────────────

    function test_sendReputationUpdate_deliversToAnchor() public {
        IReputationAnchor.ReputationData memory data = _sampleData(500);

        vm.prank(strategy);
        baseOApp.sendReputationUpdate{ value: 0 }(
            KITE_EID, strategy, IReputationAnchor.ActorType.STRATEGY, data, ""
        );

        baseEndpoint.deliverTo(address(kiteOApp), _addrToBytes32(address(baseOApp)));

        assertEq(anchor.callCount(), 1, "anchor-not-called");
        (address actor,, int256 score,) = anchor.lastCall();
        assertEq(actor, strategy);
        assertEq(score, 500);
        assertEq(kiteOApp.lastSeqIn(BASE_EID, strategy), 1);
    }

    function test_replay_secondDeliveryReverts() public {
        IReputationAnchor.ReputationData memory data = _sampleData(500);
        vm.prank(strategy);
        baseOApp.sendReputationUpdate(
            KITE_EID, strategy, IReputationAnchor.ActorType.STRATEGY, data, ""
        );
        baseEndpoint.deliverTo(address(kiteOApp), _addrToBytes32(address(baseOApp)));

        // Replay the same packet — receiver must reject by seq.
        vm.expectRevert(
            abi.encodeWithSelector(
                IHeliosOApp.ReplaySeq.selector, BASE_EID, strategy, uint64(1), uint64(1)
            )
        );
        baseEndpoint.deliverTo(address(kiteOApp), _addrToBytes32(address(baseOApp)));
    }

    function test_peerNotSetReverts() public {
        // baseOApp has KITE peer; sending to a stranger EID should revert.
        IReputationAnchor.ReputationData memory data = _sampleData(1);
        vm.expectRevert(abi.encodeWithSelector(IHeliosOApp.PeerNotSet.selector, uint32(99_999)));
        vm.prank(strategy);
        baseOApp.sendReputationUpdate(
            99_999, strategy, IReputationAnchor.ActorType.STRATEGY, data, ""
        );
    }

    // ── Phase-5 review C1/C2: caller gates ─────────────────────────

    function test_sendReputationUpdate_revertsForUnauthorizedCaller() public {
        IReputationAnchor.ReputationData memory data = _sampleData(1);
        address rogue = address(0xDEAD);
        vm.expectRevert(abi.encodeWithSelector(IHeliosOApp.NotStrategyVault.selector, rogue));
        vm.prank(rogue);
        baseOApp.sendReputationUpdate(
            KITE_EID, rogue, IReputationAnchor.ActorType.STRATEGY, data, ""
        );
    }

    function test_sendReputationUpdate_revertsWhenActorMismatch() public {
        IReputationAnchor.ReputationData memory data = _sampleData(1);
        address victim = address(0xBADBAD);
        // `strategyVault` is allowlisted but tries to attest a different actor.
        vm.expectRevert(
            abi.encodeWithSelector(IHeliosOApp.CallerActorMismatch.selector, strategyVault, victim)
        );
        vm.prank(strategyVault);
        baseOApp.sendReputationUpdate(
            KITE_EID, victim, IReputationAnchor.ActorType.STRATEGY, data, ""
        );
    }

    function test_bridgeAndDeploy_revertsForUnauthorizedCaller() public {
        address rogue = address(0xDEAD);
        vm.expectRevert(abi.encodeWithSelector(IHeliosOApp.NotStrategyVault.selector, rogue));
        vm.prank(rogue);
        baseOApp.bridgeAndDeploy(KITE_EID, rogue, 1_000_000, "");
    }

    function test_bridgeAndDeploy_revertsWhenStrategyMismatch() public {
        address victim = address(0xBADBAD);
        vm.expectRevert(
            abi.encodeWithSelector(IHeliosOApp.CallerActorMismatch.selector, strategyVault, victim)
        );
        vm.prank(strategyVault);
        baseOApp.bridgeAndDeploy(KITE_EID, victim, 1_000_000, "");
    }

    // ── Queue / flush attestations ────────────────────────────────

    function test_queueAndFlushBatch() public {
        IReputationAnchor.ReputationData memory d1 = _sampleData(100);
        IReputationAnchor.ReputationData memory d2 = _sampleData(200);

        vm.prank(strategyVault);
        baseOApp.queueAttestation(strategy, d1);
        vm.prank(strategyVault);
        baseOApp.queueAttestation(strategy, d2);

        assertEq(baseOApp.pendingCount(strategy), 2);

        baseOApp.flushAttestationsFor(strategy, KITE_EID, "");
        assertEq(baseOApp.pendingCount(strategy), 0, "queue-not-cleared");

        baseEndpoint.deliverTo(address(kiteOApp), _addrToBytes32(address(baseOApp)));
        assertEq(anchor.callCount(), 2, "expect-two-anchor-calls");
        assertEq(kiteOApp.lastSeqIn(BASE_EID, strategy), 2, "seq-not-advanced");
    }

    function test_queueAttestation_onlyAllowlistedVault() public {
        IReputationAnchor.ReputationData memory d = _sampleData(1);
        address rogue = address(0xDEAD);
        vm.expectRevert(abi.encodeWithSelector(IHeliosOApp.NotStrategyVault.selector, rogue));
        vm.prank(rogue);
        baseOApp.queueAttestation(strategy, d);
    }

    function test_queueFull_rejectsOverCap() public {
        vm.prank(owner);
        baseOApp.setMaxPendingPerStrategy(2);
        IReputationAnchor.ReputationData memory d = _sampleData(1);

        vm.prank(strategyVault);
        baseOApp.queueAttestation(strategy, d);
        vm.prank(strategyVault);
        baseOApp.queueAttestation(strategy, d);

        vm.expectRevert(
            abi.encodeWithSelector(IHeliosOApp.QueueFull.selector, strategy, uint256(2))
        );
        vm.prank(strategyVault);
        baseOApp.queueAttestation(strategy, d);
    }

    function test_flush_emptyQueueReverts() public {
        vm.expectRevert(abi.encodeWithSelector(IHeliosOApp.EmptyQueue.selector, strategy));
        baseOApp.flushAttestationsFor(strategy, KITE_EID, "");
    }

    // ── Quote sanity ───────────────────────────────────────────────

    function test_quote_reflectsEndpointFee() public {
        kiteEndpoint.setFee(1 ether, 0, address(0));
        // quote() doesn't actually need a peer — but our send guards do.
        IReputationAnchor.ReputationData memory data = _sampleData(1);
        bytes memory payload = CrossChainCodec.encodeReputationUpdate(
            CrossChainCodec.ReputationUpdateV1({
                seq: 1, actor: strategy, actorType: IReputationAnchor.ActorType.STRATEGY, data: data
            })
        );
        IHeliosOApp.MessagingFee memory fee = kiteOApp.quote(BASE_EID, payload, "");
        assertEq(fee.nativeFee, 1 ether);
    }

    // ── Helpers ────────────────────────────────────────────────────

    function _sampleData(int256 score)
        internal
        pure
        returns (IReputationAnchor.ReputationData memory)
    {
        return IReputationAnchor.ReputationData({
            currentScore: score,
            lastUpdateBlock: 1,
            totalAttestedTrades: 1,
            totalRealizedPnL: 100,
            maxDrawdownBps: 50,
            proofValidityRateBps: 10_000,
            actorType: IReputationAnchor.ActorType.STRATEGY,
            componentsHash: bytes32(uint256(0xfeed))
        });
    }

    function _addrToBytes32(address a) internal pure returns (bytes32) {
        return bytes32(uint256(uint160(a)));
    }

    function _decodeAsReputation(bytes calldata encoded) external pure {
        CrossChainCodec.decodeReputationUpdate(encoded);
    }
}
