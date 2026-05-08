// Shared helpers for Helios mappings.

import { BigInt, ByteArray, Bytes, crypto, dataSource, ethereum, log } from "@graphprotocol/graph-ts";
import { Allocator, Strategy, User, UserDelegation } from "../generated/schema";

// Canonical chain ids. Mappings should call `currentChainId()` which
// resolves through the active datasource's network context — these
// constants are exported so the cross-chain handler can branch on
// "is this Kite, the canonical anchor?" without re-resolving.
export const KITE_TESTNET_CHAIN_ID: i32 = 2368;
export const BASE_SEPOLIA_CHAIN_ID: i32 = 84532;
export const ARBITRUM_SEPOLIA_CHAIN_ID: i32 = 421614;

// Phase-5 / WS6 — replaces the Phase-1 PHASE1_CHAIN_ID constant. Maps a
// graph-cli network slug (declared in subgraph.yaml `network:` field) to
// the on-chain `chainId`. Must stay in sync with both the manifest and
// `frontend/src/lib/chains.ts` so subgraph rows align with the chain
// dropdown values the frontend filters on.
//
// Unknown networks return zero (subgraph indexer should never observe
// this; we surface it via a debug log instead of reverting so a typo in
// `subgraph.yaml` produces a queryable signal rather than a hard halt).
export function chainIdForNetwork(network: string): i32 {
  if (network == "kite-ai-testnet") return KITE_TESTNET_CHAIN_ID;
  if (network == "base-sepolia") return BASE_SEPOLIA_CHAIN_ID;
  if (network == "arbitrum-sepolia") return ARBITRUM_SEPOLIA_CHAIN_ID;
  log.warning("chainIdForNetwork: unknown network slug {}", [network]);
  return 0;
}

export function currentChainId(): i32 {
  return chainIdForNetwork(dataSource.network());
}

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
  s.executingChainIds = [];
  return s;
}

// Phase-5 / WS6 — add a chainId to a strategy's `executingChainIds`
// list iff it isn't already present. The frontend filters strategies
// by the chains they actually execute on (Kite-only vs Base/Arb-also)
// without joining against the trade table.
export function recordExecutingChain(strategy: Strategy, chainId: i32): void {
  if (chainId == 0) return;
  const existing = strategy.executingChainIds;
  for (let i = 0; i < existing.length; i++) {
    if (existing[i] == chainId) return;
  }
  existing.push(chainId);
  strategy.executingChainIds = existing;
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
