// Shared helpers for Helios mappings.

import { BigInt, ByteArray, Bytes, crypto, ethereum, log } from "@graphprotocol/graph-ts";
import { Allocator, Strategy, User, UserDelegation } from "../generated/schema";

// Phase 1 ships Kite testnet only. Phase 5 adds Base/Arbitrum Sepolia and
// will need to read chainId from the network context, not this constant.
// Grep for PHASE1_CHAIN_ID before promoting this subgraph to multichain.
export const PHASE1_CHAIN_ID: i32 = 2368;

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

// Phase 3 / WS5.B — `UserDelegation.id = keccak256(user || allocator)`.
// One row per (user, allocator) pair; upserted on each allocation event.
export function delegationId(user: Bytes, allocator: Bytes): Bytes {
  const buf = new ByteArray(user.length + allocator.length);
  for (let i = 0; i < user.length; i++) buf[i] = user[i];
  for (let i = 0; i < allocator.length; i++) buf[user.length + i] = allocator[i];
  return Bytes.fromByteArray(crypto.keccak256(buf));
}

export function getOrCreateDelegation(
  user: Bytes,
  allocator: Bytes,
  blockTimestamp: BigInt,
): UserDelegation {
  const id = delegationId(user, allocator);
  const existing = UserDelegation.load(id);
  if (existing != null) {
    return existing;
  }
  const d = new UserDelegation(id);
  d.user = user;
  d.allocator = allocator;
  d.capital = BigInt.zero();
  d.since = blockTimestamp;
  return d;
}

// Suppress unused-export warnings when graph build's tree-shaker is overzealous.
export function _ping(): void {
  log.debug("helpers loaded", []);
}
