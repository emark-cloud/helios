import { BigInt, Bytes } from "@graphprotocol/graph-ts";
import {
  ReputationPosted,
  CrossChainReputationPosted,
  ComponentsAnchored,
  CrossChainTradeTick,
} from "../generated/ReputationAnchorV2/ReputationAnchorV2";
import {
  ComponentsAnchor,
  CrossChainReputationMessage,
  ReputationSnapshot,
} from "../generated/schema";
import { getOrCreateAllocator, getOrCreateStrategy, logEventId } from "./helpers";

// Mirrors IReputationAnchor.ActorType — same enum order as V1.
const ACTOR_STRATEGY: i32 = 0;
const ACTOR_ALLOCATOR: i32 = 1;

function actorTypeLabel(t: i32): string {
  if (t == ACTOR_STRATEGY) return "STRATEGY";
  if (t == ACTOR_ALLOCATOR) return "ALLOCATOR";
  return "UNKNOWN";
}

// V2's ReputationPosted matches V1's signature 1:1; the only on-chain
// difference is the EIP-712 typehash binds `componentsHash` (separately
// emitted via ComponentsAnchored). Snapshot is stamped `source = "V2"`
// so consumers can join with the per-update ComponentsAnchor row.
export function handleReputationPostedV2(event: ReputationPosted): void {
  const actor = event.params.actor as Bytes;
  const actorType: i32 = event.params.actorType;
  const score = event.params.newScore;

  const snapshot = new ReputationSnapshot(logEventId(event));
  snapshot.actor = actor;
  snapshot.actorType = actorTypeLabel(actorType);
  snapshot.score = score;
  snapshot.totalAttestedTrades = BigInt.zero();
  snapshot.totalRealizedPnL = BigInt.zero();
  snapshot.maxDrawdownBps = 0;
  snapshot.proofValidityRateBps = 0;
  snapshot.timestamp = event.block.timestamp;
  snapshot.blockNumber = event.block.number;
  snapshot.source = "V2";
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

export function handleCrossChainReputationPostedV2(event: CrossChainReputationPosted): void {
  const msg = new CrossChainReputationMessage(logEventId(event));
  msg.srcEid = event.params.srcEid.toI32();
  msg.dstEid = 0;
  msg.actor = event.params.actor as Bytes;
  msg.actorType = actorTypeLabel(event.params.actorType);
  msg.score = event.params.newScore;
  msg.sentAt = BigInt.zero();
  msg.receivedAt = event.block.timestamp;
  msg.save();
}

// WS11 — cross-chain batch trade tick. Counter-only; bumps the
// strategy's totalAttestedTrades without writing the score. Mirrored
// from `ReputationAnchorV2.postCrossChainTradeTick`.
export function handleCrossChainTradeTick(event: CrossChainTradeTick): void {
  const actor = event.params.actor as Bytes;
  const newTotal = event.params.newTotalAttestedTrades;
  const s = getOrCreateStrategy(actor, event.block.timestamp);
  s.totalAttestedTrades = newTotal.toI32();
  s.save();

  const snapshot = new ReputationSnapshot(logEventId(event));
  snapshot.actor = actor;
  snapshot.actorType = "STRATEGY";
  snapshot.score = s.currentReputation;
  snapshot.totalAttestedTrades = newTotal;
  snapshot.totalRealizedPnL = BigInt.zero();
  snapshot.maxDrawdownBps = 0;
  snapshot.proofValidityRateBps = 0;
  snapshot.timestamp = event.block.timestamp;
  snapshot.blockNumber = event.block.number;
  snapshot.source = "V2_xchain_tick";
  snapshot.save();
}

// Paired 1:1 with `ReputationPosted` on V2. The audit page joins
// `(actor, timestamp)` to surface the componentsHash alongside the
// score so the §8.2 sub-score breakdown can be tamper-checked.
export function handleComponentsAnchored(event: ComponentsAnchored): void {
  const row = new ComponentsAnchor(logEventId(event));
  row.actor = event.params.actor as Bytes;
  row.componentsHash = event.params.componentsHash;
  row.timestamp = event.block.timestamp;
  row.blockNumber = event.block.number;
  row.txHash = event.transaction.hash;
  row.save();
}
