// Shared helpers for Helios mappings.

import { BigInt, Bytes, ethereum, log } from "@graphprotocol/graph-ts";
import { Strategy, Allocator, User } from "../generated/schema";

export function logEventId(event: ethereum.Event): Bytes {
  return event.transaction.hash.concatI32(event.logIndex.toI32());
}

export function getOrCreateStrategy(strategyId: Bytes, blockTimestamp: BigInt): Strategy {
  const existing = Strategy.load(strategyId);
  if (existing != null) {
    return existing;
  }
  const s = new Strategy(strategyId);
  s.operator = Bytes.empty();
  s.declaredClass = "";
  s.chainId = 0;
  s.stakeAmount = BigInt.zero();
  s.feeRateBps = 0;
  s.maxCapacity = BigInt.zero();
  s.active = true;
  s.registeredAt = blockTimestamp;
  s.currentReputation = BigInt.zero();
  s.totalRealizedPnL = BigInt.zero();
  s.totalAttestedTrades = 0;
  s.maxDrawdownBps = 0;
  return s;
}

export function getOrCreateAllocator(allocatorId: Bytes, blockTimestamp: BigInt): Allocator {
  const existing = Allocator.load(allocatorId);
  if (existing != null) {
    return existing;
  }
  const a = new Allocator(allocatorId);
  a.name = "";
  a.operator = Bytes.empty();
  a.feeRateBps = 0;
  a.stakeAmount = BigInt.zero();
  a.isReferenceBrand = false;
  a.active = true;
  a.registeredAt = blockTimestamp;
  a.totalUsers = 0;
  a.totalCapitalManaged = BigInt.zero();
  a.currentReputation = BigInt.zero();
  return a;
}

export function getOrCreateUser(userId: Bytes, blockTimestamp: BigInt): User {
  const existing = User.load(userId);
  if (existing != null) {
    return existing;
  }
  const u = new User(userId);
  u.createdAt = blockTimestamp;
  return u;
}

// Stable hex digits → readable hex string.
export function bytesToHex(b: Bytes): string {
  return b.toHexString();
}

// Suppress unused-export warnings when graph build's tree-shaker is overzealous.
export function _ping(): void {
  log.debug("helpers loaded", []);
}
