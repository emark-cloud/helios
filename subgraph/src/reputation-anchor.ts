import { BigInt, Bytes } from "@graphprotocol/graph-ts";
import {
  ReputationPosted,
  CrossChainReputationPosted,
} from "../generated/ReputationAnchor/ReputationAnchor";
import { ReputationSnapshot, CrossChainReputationMessage } from "../generated/schema";
import { getOrCreateAllocator, getOrCreateStrategy, logEventId } from "./helpers";

// Mirrors IReputationAnchor.ActorType — keep in sync with the Solidity enum order.
const ACTOR_STRATEGY: i32 = 0;
const ACTOR_ALLOCATOR: i32 = 1;

function actorTypeLabel(t: i32): string {
  if (t == ACTOR_STRATEGY) return "STRATEGY";
  if (t == ACTOR_ALLOCATOR) return "ALLOCATOR";
  return "UNKNOWN";
}

export function handleReputationPosted(event: ReputationPosted): void {
  const actor = event.params.actor as Bytes;
  const actorType: i32 = event.params.actorType;
  const score = event.params.newScore;

  const snapshot = new ReputationSnapshot(logEventId(event));
  snapshot.actor = actor;
  snapshot.actorType = actorTypeLabel(actorType);
  snapshot.score = score;
  // Phase 1: aggregates are computed off-chain by the reputation engine and are
  // only included in the snapshot if they were part of the on-chain payload.
  // We capture zeros here and let the engine populate via subsequent events.
  snapshot.totalAttestedTrades = BigInt.zero();
  snapshot.totalRealizedPnL = BigInt.zero();
  snapshot.maxDrawdownBps = 0;
  snapshot.proofValidityRateBps = 0;
  snapshot.timestamp = event.block.timestamp;
  snapshot.blockNumber = event.block.number;
  snapshot.save();

  if (actorType == ACTOR_STRATEGY) {
    const s = getOrCreateStrategy(actor, event.block.timestamp);
    s.currentReputation = score;
    s.save();
  } else if (actorType == ACTOR_ALLOCATOR) {
    const a = getOrCreateAllocator(actor, event.block.timestamp);
    a.currentReputation = score;
    a.save();
  }
}

export function handleCrossChainReputationPosted(event: CrossChainReputationPosted): void {
  // Phase 1 is single-chain — we still capture inbound LayerZero deliveries so
  // the entity history reads cleanly once Phase 5 stands up the OApp.
  const id = logEventId(event);
  const msg = new CrossChainReputationMessage(id);
  msg.srcEid = event.params.srcEid.toI32();
  msg.dstEid = 0;
  msg.actor = event.params.actor as Bytes;
  msg.actorType = actorTypeLabel(event.params.actorType);
  msg.score = event.params.newScore;
  msg.sentAt = BigInt.zero();
  msg.receivedAt = event.block.timestamp;
  msg.save();
}
