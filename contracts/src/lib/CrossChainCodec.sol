// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { IReputationAnchor } from "../interfaces/IReputationAnchor.sol";

/// @notice Wire format for cross-chain Helios messages. All three chains decode
///         identically. Layout is versioned by the leading PayloadKind byte;
///         bumping a kind requires a v2 entry, never a silent change.
///
///         Helios.md §6.9, §12; phase5-plan.md §WS1.
library CrossChainCodec {
    /// @dev Tag for the leading byte. Distinct values required.
    enum PayloadKind {
        Invalid, // 0 reserved so an all-zero payload can never decode
        ReputationUpdateV1,
        BridgeDeployV1
    }

    /// @notice Reputation message body. `seq` is per-(srcEid, strategy) and is
    ///         compared against `lastSeqIn` on the receiver to reject replays.
    struct ReputationUpdateV1 {
        uint64 seq;
        address actor;
        IReputationAnchor.ActorType actorType;
        IReputationAnchor.ReputationData data;
    }

    /// @notice One row inside a batched reputation flush. The flush message itself
    ///         is `(PayloadKind.ReputationUpdateV1, batch[])`; per-row seq numbers
    ///         are validated independently on the receiver.
    struct ReputationBatchEntry {
        uint64 seq;
        address strategy;
        IReputationAnchor.ReputationData data;
    }

    /// @notice Capital path: source chain has burned `amount` of mock USDC OFT,
    ///         destination chain credits `strategyOnDst` once it sees this payload.
    struct BridgeDeployV1 {
        uint64 seq;
        address strategy;
        uint256 amount;
    }

    error UnknownKind(uint8 kind);
    error EmptyBatch();

    // -- Single reputation update (sendReputationUpdate) ---------------------

    function encodeReputationUpdate(ReputationUpdateV1 memory update)
        internal
        pure
        returns (bytes memory)
    {
        return abi.encode(
            PayloadKind.ReputationUpdateV1, update.seq, update.actor, update.actorType, update.data
        );
    }

    function decodeReputationUpdate(bytes calldata payload)
        internal
        pure
        returns (ReputationUpdateV1 memory update)
    {
        (
            PayloadKind kind,
            uint64 seq,
            address actor,
            IReputationAnchor.ActorType actorType,
            IReputationAnchor.ReputationData memory data
        ) = abi.decode(
            payload,
            (
                PayloadKind,
                uint64,
                address,
                IReputationAnchor.ActorType,
                IReputationAnchor.ReputationData
            )
        );
        if (kind != PayloadKind.ReputationUpdateV1) revert UnknownKind(uint8(kind));
        update.seq = seq;
        update.actor = actor;
        update.actorType = actorType;
        update.data = data;
    }

    // -- Batched flush (flushAttestations) -----------------------------------

    function encodeReputationBatch(ReputationBatchEntry[] memory entries)
        internal
        pure
        returns (bytes memory)
    {
        if (entries.length == 0) revert EmptyBatch();
        return abi.encode(PayloadKind.ReputationUpdateV1, entries);
    }

    function decodeReputationBatch(bytes calldata payload)
        internal
        pure
        returns (ReputationBatchEntry[] memory entries)
    {
        (PayloadKind kind, ReputationBatchEntry[] memory decoded) =
            abi.decode(payload, (PayloadKind, ReputationBatchEntry[]));
        if (kind != PayloadKind.ReputationUpdateV1) revert UnknownKind(uint8(kind));
        entries = decoded;
    }

    // -- Bridge & deploy -----------------------------------------------------

    function encodeBridgeDeploy(BridgeDeployV1 memory body) internal pure returns (bytes memory) {
        return abi.encode(PayloadKind.BridgeDeployV1, body.seq, body.strategy, body.amount);
    }

    function decodeBridgeDeploy(bytes calldata payload)
        internal
        pure
        returns (BridgeDeployV1 memory body)
    {
        (PayloadKind kind, uint64 seq, address strategy, uint256 amount) =
            abi.decode(payload, (PayloadKind, uint64, address, uint256));
        if (kind != PayloadKind.BridgeDeployV1) revert UnknownKind(uint8(kind));
        body.seq = seq;
        body.strategy = strategy;
        body.amount = amount;
    }

    // -- Routing helper ------------------------------------------------------

    /// @notice Peek the leading kind byte without fully decoding. Receivers branch
    ///         on this before calling the matching decoder.
    function peekKind(bytes calldata payload) internal pure returns (PayloadKind kind) {
        // ABI-encoded enums occupy the first 32-byte word.
        uint8 raw;
        assembly ("memory-safe") {
            raw := byte(31, calldataload(payload.offset))
        }
        if (raw == 0 || raw > uint8(PayloadKind.BridgeDeployV1)) revert UnknownKind(raw);
        kind = PayloadKind(raw);
    }
}
