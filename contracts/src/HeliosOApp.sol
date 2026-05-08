// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {
    OApp,
    MessagingFee as LzMessagingFee,
    MessagingReceipt,
    Origin
} from "@layerzerolabs/oapp-evm/oapp/OApp.sol";
import { Ownable } from "@openzeppelin/contracts/access/Ownable.sol";

import { IHeliosOApp } from "./interfaces/IHeliosOApp.sol";
import { IReputationAnchor } from "./interfaces/IReputationAnchor.sol";
import { CrossChainCodec } from "./lib/CrossChainCodec.sol";

/// @notice Cross-chain glue for Helios. On the canonical chain (Kite) it forwards
///         inbound reputation updates into ReputationAnchor and credits inbound
///         capital into a strategy. On execution chains (Base/Arb) it accepts
///         attestations from local StrategyVaults, batches them, and ships the
///         batch back to Kite.
///
///         Helios.md §6.9, §12; phase5-plan.md §WS1.
contract HeliosOApp is OApp, IHeliosOApp {
    /// @notice Endpoint id of the canonical chain. Reputation messages are only
    ///         routed here from execution chains; bridgeAndDeploy fans out from here.
    uint32 public immutable kiteEid;

    /// @notice Reputation anchor on the canonical chain. address(0) on execution chains.
    IReputationAnchor public immutable reputationAnchor;

    /// @notice Optional callback invoked on receipt of a BridgeDeployV1 payload.
    ///         Lives on execution chains; on the canonical chain it’s typically zero.
    address public bridgeReceiver;

    /// @notice Allowlist of local StrategyVaults permitted to queue attestations.
    mapping(address strategyVault => bool allowed) public isStrategyVault;

    /// @notice Replay window per (srcEid, actor). Both ReputationUpdateV1 and
    ///         BridgeDeployV1 advance this counter — they share the namespace
    ///         keyed on the strategy address.
    mapping(uint32 srcEid => mapping(address actor => uint64 lastSeq)) public lastSeqIn;

    /// @notice Monotonic per-strategy out-bound counter. Bumped every time we
    ///         queue an attestation on this chain, so receivers can detect drops.
    mapping(address strategy => uint64 seq) public lastSeqOut;

    /// @notice Pending attestation buffer per strategy, awaiting flush.
    mapping(address strategy => CrossChainCodec.ReputationBatchEntry[]) internal _pending;

    /// @notice Anti-spam cap on the pending queue; over-cap reverts queueAttestation
    ///         until flushAttestations clears it.
    uint256 public maxPendingPerStrategy;

    constructor(
        address endpoint_,
        address delegate_,
        uint32 kiteEid_,
        address reputationAnchor_,
        uint256 maxPendingPerStrategy_
    ) OApp(endpoint_, delegate_) Ownable(delegate_) {
        kiteEid = kiteEid_;
        reputationAnchor = IReputationAnchor(reputationAnchor_);
        maxPendingPerStrategy = maxPendingPerStrategy_ == 0 ? 64 : maxPendingPerStrategy_;
    }

    // ── Admin ───────────────────────────────────────────────────────

    function setStrategyVault(address vault, bool allowed) external onlyOwner {
        isStrategyVault[vault] = allowed;
    }

    function setBridgeReceiver(address receiver) external onlyOwner {
        bridgeReceiver = receiver;
    }

    function setMaxPendingPerStrategy(uint256 cap) external onlyOwner {
        require(cap > 0, "cap=0");
        maxPendingPerStrategy = cap;
    }

    // ── Send: single reputation update ──────────────────────────────

    function sendReputationUpdate(
        uint32 dstEid,
        address actor,
        IReputationAnchor.ActorType actorType,
        IReputationAnchor.ReputationData calldata data,
        bytes calldata options
    ) external payable {
        // Phase-5 review C1: a vault on Base/Arb may only attest its own
        // reputation. Without this gate, any address on a remote chain could
        // forge an arbitrary `actor` + `data` blob to overwrite reputation on
        // Kite (the LZ peer is trusted, the OApp's caller is not).
        if (!isStrategyVault[msg.sender]) revert NotStrategyVault(msg.sender);
        if (actor != msg.sender) revert CallerActorMismatch(msg.sender, actor);

        if (peers[dstEid] == bytes32(0)) {
            revert PeerNotSet(dstEid);
        }

        uint64 nextSeq = lastSeqOut[actor] + 1;
        lastSeqOut[actor] = nextSeq;

        bytes memory payload = CrossChainCodec.encodeReputationUpdate(
            CrossChainCodec.ReputationUpdateV1({
                seq: nextSeq, actor: actor, actorType: actorType, data: data
            })
        );

        MessagingReceipt memory receipt = _lzSend(
            dstEid,
            payload,
            options,
            LzMessagingFee({ nativeFee: msg.value, lzTokenFee: 0 }),
            payable(msg.sender)
        );

        emit ReputationMessageSent(dstEid, actor, actorType, receipt.guid);
    }

    // ── Send: batched attestation queue (StrategyVault-driven) ──────

    function queueAttestation(address strategy, IReputationAnchor.ReputationData calldata data)
        external
    {
        if (!isStrategyVault[msg.sender]) revert NotStrategyVault(msg.sender);

        CrossChainCodec.ReputationBatchEntry[] storage queue = _pending[strategy];
        if (queue.length >= maxPendingPerStrategy) {
            revert QueueFull(strategy, maxPendingPerStrategy);
        }

        uint64 nextSeq = lastSeqOut[strategy] + 1;
        lastSeqOut[strategy] = nextSeq;

        queue.push(
            CrossChainCodec.ReputationBatchEntry({ seq: nextSeq, strategy: strategy, data: data })
        );

        emit AttestationQueued(strategy, nextSeq, queue.length);
    }

    /// @notice Flush a specific strategy’s attestation queue. The expected
    ///         caller is a keeper that knows which strategies have pending data.
    function flushAttestationsFor(address strategy, uint32 dstEid, bytes calldata options)
        external
        payable
        returns (bytes32 guid)
    {
        if (peers[dstEid] == bytes32(0)) revert PeerNotSet(dstEid);

        CrossChainCodec.ReputationBatchEntry[] storage queue = _pending[strategy];
        uint256 n = queue.length;
        if (n == 0) revert EmptyQueue(strategy);

        CrossChainCodec.ReputationBatchEntry[] memory batch =
            new CrossChainCodec.ReputationBatchEntry[](n);
        uint64 firstSeq = queue[0].seq;
        uint64 lastSeq = queue[n - 1].seq;
        for (uint256 i = 0; i < n; i++) {
            batch[i] = queue[i];
        }
        delete _pending[strategy];

        bytes memory payload = CrossChainCodec.encodeReputationBatch(batch);
        MessagingReceipt memory receipt = _lzSend(
            dstEid,
            payload,
            options,
            LzMessagingFee({ nativeFee: msg.value, lzTokenFee: 0 }),
            payable(msg.sender)
        );
        guid = receipt.guid;

        emit AttestationsFlushed(dstEid, n, firstSeq, lastSeq, guid);
    }

    // ── Send: capital path ──────────────────────────────────────────

    function bridgeAndDeploy(
        uint32 dstEid,
        address strategyOnDst,
        uint256 amount,
        bytes calldata options
    ) external payable {
        // Phase-5 review C2: only an allowlisted local vault can originate a
        // bridge-and-deploy, and only to its own address on the destination
        // chain. Today `bridgeReceiver` is unset so the on-chain effect is a
        // no-op, but once wired this gate prevents any address from forging a
        // capital credit for an arbitrary strategy.
        if (!isStrategyVault[msg.sender]) revert NotStrategyVault(msg.sender);
        if (strategyOnDst != msg.sender) revert CallerActorMismatch(msg.sender, strategyOnDst);

        if (peers[dstEid] == bytes32(0)) revert PeerNotSet(dstEid);

        uint64 nextSeq = lastSeqOut[strategyOnDst] + 1;
        lastSeqOut[strategyOnDst] = nextSeq;

        bytes memory payload = CrossChainCodec.encodeBridgeDeploy(
            CrossChainCodec.BridgeDeployV1({
                seq: nextSeq, strategy: strategyOnDst, amount: amount
            })
        );

        MessagingReceipt memory receipt = _lzSend(
            dstEid,
            payload,
            options,
            LzMessagingFee({ nativeFee: msg.value, lzTokenFee: 0 }),
            payable(msg.sender)
        );

        emit BridgeAndDeploySent(dstEid, strategyOnDst, amount, receipt.guid);
    }

    // ── Receive: dispatch by payload kind ───────────────────────────

    function _lzReceive(
        Origin calldata origin,
        bytes32 guid,
        bytes calldata message,
        address, /*executor*/
        bytes calldata /*extraData*/
    ) internal override {
        CrossChainCodec.PayloadKind kind = CrossChainCodec.peekKind(message);

        if (kind == CrossChainCodec.PayloadKind.ReputationUpdateV1) {
            // Could be either single-update or batched. Discriminate by trying
            // batch decode first — abi.decode reverts on shape mismatch, so we
            // fall through to single decode in a try/catch-style guard via the
            // codec: encoders set a different shape for each.
            // Cheaper: peek the second word — for the single shape it’s a uint64
            // seq; for the batch shape it’s a 0x40 offset to the dynamic array.
            uint256 second;
            assembly ("memory-safe") {
                second := calldataload(add(message.offset, 32))
            }
            if (second == 0x40) {
                _handleReputationBatch(origin, guid, message);
            } else {
                _handleReputationSingle(origin, guid, message);
            }
        } else if (kind == CrossChainCodec.PayloadKind.BridgeDeployV1) {
            _handleBridgeDeploy(origin, guid, message);
        } else {
            revert UnknownPayloadKind(uint8(kind));
        }
    }

    function _handleReputationSingle(Origin calldata origin, bytes32 guid, bytes calldata message)
        internal
    {
        CrossChainCodec.ReputationUpdateV1 memory update =
            CrossChainCodec.decodeReputationUpdate(message);
        _applyReputation(
            origin.srcEid, update.actor, update.seq, update.actorType, update.data, guid
        );
    }

    function _handleReputationBatch(Origin calldata origin, bytes32 guid, bytes calldata message)
        internal
    {
        CrossChainCodec.ReputationBatchEntry[] memory batch =
            CrossChainCodec.decodeReputationBatch(message);
        for (uint256 i = 0; i < batch.length; i++) {
            _applyReputation(
                origin.srcEid,
                batch[i].strategy,
                batch[i].seq,
                IReputationAnchor.ActorType.STRATEGY,
                batch[i].data,
                guid
            );
        }
    }

    function _applyReputation(
        uint32 srcEid,
        address actor,
        uint64 seq,
        IReputationAnchor.ActorType actorType,
        IReputationAnchor.ReputationData memory data,
        bytes32 guid
    ) internal {
        uint64 last = lastSeqIn[srcEid][actor];
        if (seq <= last) revert ReplaySeq(srcEid, actor, seq, last);
        lastSeqIn[srcEid][actor] = seq;

        if (address(reputationAnchor) != address(0)) {
            reputationAnchor.postCrossChainUpdate(actor, actorType, data);
        }

        emit ReputationMessageReceived(srcEid, actor, actorType, guid);
    }

    function _handleBridgeDeploy(Origin calldata origin, bytes32 guid, bytes calldata message)
        internal
    {
        CrossChainCodec.BridgeDeployV1 memory body = CrossChainCodec.decodeBridgeDeploy(message);
        uint64 last = lastSeqIn[origin.srcEid][body.strategy];
        if (body.seq <= last) revert ReplaySeq(origin.srcEid, body.strategy, body.seq, last);
        lastSeqIn[origin.srcEid][body.strategy] = body.seq;

        address receiver = bridgeReceiver;
        if (receiver != address(0)) {
            IBridgeReceiver(receiver).onBridgeAndDeploy(body.strategy, body.amount);
        }

        emit BridgeAndDeployReceived(origin.srcEid, body.strategy, body.amount, guid);
    }

    // ── Quoting + helpers ───────────────────────────────────────────

    function quote(uint32 dstEid, bytes calldata payload, bytes calldata options)
        external
        view
        returns (IHeliosOApp.MessagingFee memory)
    {
        LzMessagingFee memory fee = _quote(dstEid, payload, options, false);
        return IHeliosOApp.MessagingFee({ nativeFee: fee.nativeFee, lzTokenFee: fee.lzTokenFee });
    }

    function pendingCount(address strategy) external view returns (uint256) {
        return _pending[strategy].length;
    }

    function pendingAt(address strategy, uint256 i)
        external
        view
        returns (CrossChainCodec.ReputationBatchEntry memory)
    {
        return _pending[strategy][i];
    }
}

interface IBridgeReceiver {
    function onBridgeAndDeploy(address strategy, uint256 amount) external;
}
