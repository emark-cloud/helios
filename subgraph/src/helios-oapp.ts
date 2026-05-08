// Phase 5 / WS6 — HeliosOApp cross-chain reputation message mapping.
//
// The OApp emits four events relevant to the subgraph:
//
//   * `AttestationQueued(strategy, seq, queueLength)` — fires on a
//     non-canonical chain when a StrategyVault forwards an attestation
//     after a successful `executeWithProof`. Touches the strategy
//     entity so the local datasource has a row to resolve.
//
//   * `AttestationsFlushed(dstEid, batchSize, firstSeq, lastSeq, guid)`
//     — fires on the source chain when a queued batch is `_lzSend`ed.
//     Writes a `CrossChainReputationMessage` row keyed by GUID with
//     `sentAt` populated.
//
//   * `ReputationMessageReceived(srcEid, actor, actorType, guid)` —
//     fires on Kite when `_lzReceive` decodes the batch and posts the
//     accumulated update through `ReputationAnchor.postCrossChainUpdate`.
//     Loads the row by GUID and stamps `receivedAt` + `dstChainId`.
//
//   * `ReputationMessageSent(dstEid, actor, actorType, guid)` —
//     emitted by the optional one-shot `sendReputationUpdate` path.
//     Same shape as the flushed batch from the subgraph's perspective.

import { BigInt, Bytes, log } from "@graphprotocol/graph-ts";
import {
  AttestationsFlushed,
  AttestationQueued,
  ReputationMessageReceived,
  ReputationMessageSent,
} from "../generated/HeliosOApp/HeliosOApp";
import { CrossChainReputationMessage } from "../generated/schema";
import { currentChainId, getOrCreateStrategy, KITE_TESTNET_CHAIN_ID } from "./helpers";

function actorTypeName(actorType: i32): string {
  if (actorType == 0) {
    return "STRATEGY";
  }
  return "ALLOCATOR";
}

export function handleAttestationQueued(event: AttestationQueued): void {
  // Touch the strategy on this chain so the indexer has a row to
  // resolve once a follow-up TradeAttested arrives.
  getOrCreateStrategy(event.params.strategy as Bytes, event.block.timestamp).save();
}

export function handleAttestationsFlushed(event: AttestationsFlushed): void {
  const guid = event.params.guid;
  let msg = CrossChainReputationMessage.load(guid);
  if (msg == null) {
    msg = new CrossChainReputationMessage(guid);
    msg.srcChainId = currentChainId();
    msg.srcEid = 0; // populated when the receive event fires
    msg.dstEid = event.params.dstEid.toI32();
    msg.actor = Bytes.empty();
    msg.actorType = "BATCH";
    msg.score = BigInt.zero();
    msg.sentAt = event.block.timestamp;
  }
  msg.save();
}

export function handleReputationMessageSent(event: ReputationMessageSent): void {
  const guid = event.params.guid;
  let msg = CrossChainReputationMessage.load(guid);
  if (msg == null) {
    msg = new CrossChainReputationMessage(guid);
    msg.srcChainId = currentChainId();
    msg.srcEid = 0;
    msg.sentAt = event.block.timestamp;
    msg.score = BigInt.zero();
  }
  msg.dstEid = event.params.dstEid.toI32();
  msg.actor = event.params.actor as Bytes;
  msg.actorType = actorTypeName(event.params.actorType);
  msg.save();
}

export function handleReputationMessageReceived(event: ReputationMessageReceived): void {
  const guid = event.params.guid;
  let msg = CrossChainReputationMessage.load(guid);
  if (msg == null) {
    // Receive may land before the source-chain mapping has caught up
    // when Goldsky indexes the two networks at different speeds — write
    // a partial row so the GUID is at least queryable.
    msg = new CrossChainReputationMessage(guid);
    msg.srcChainId = 0;
    msg.dstEid = 0;
    msg.actor = event.params.actor as Bytes;
    msg.actorType = actorTypeName(event.params.actorType);
    msg.score = BigInt.zero();
    msg.sentAt = BigInt.zero();
    log.warning("HeliosOApp: receive before send for guid {}", [guid.toHexString()]);
  }
  msg.srcEid = event.params.srcEid.toI32();
  msg.receivedAt = event.block.timestamp;
  const dst = currentChainId();
  msg.dstChainId = dst;
  msg.save();
  // Receive is expected only on Kite; surface non-canonical receptions.
  if (dst != KITE_TESTNET_CHAIN_ID) {
    log.warning("HeliosOApp: receive observed off-canonical chainId {}", [dst.toString()]);
  }
}
