import { BigInt, Bytes, crypto, ByteArray, ethereum } from "@graphprotocol/graph-ts";
import {
  AllocationCreated,
  AllocationIncreased,
  AllocationDecreased,
  StrategyDefunded,
} from "../generated/AllocatorVault/AllocatorVault";
import { Allocation, DefundEvent } from "../generated/schema";
import {
  getOrCreateAllocator,
  getOrCreateStrategy,
  getOrCreateUser,
  logEventId,
} from "./helpers";

// Allocation id = keccak(user ‖ allocator ‖ strategy). The AllocatorVault is
// itself the indexed allocator address — `event.address` — since the vault is
// per-allocator.
function allocationId(user: Bytes, allocator: Bytes, strategy: Bytes): Bytes {
  const buf = new ByteArray(user.length + allocator.length + strategy.length);
  for (let i = 0; i < user.length; i++) buf[i] = user[i];
  for (let i = 0; i < allocator.length; i++) buf[user.length + i] = allocator[i];
  for (let i = 0; i < strategy.length; i++)
    buf[user.length + allocator.length + i] = strategy[i];
  return Bytes.fromByteArray(crypto.keccak256(buf));
}

function ensureAllocation(
  user: Bytes,
  allocator: Bytes,
  strategy: Bytes,
  event: ethereum.Event,
): Allocation {
  const id = allocationId(user, allocator, strategy);
  const existing = Allocation.load(id);
  if (existing != null) {
    return existing;
  }
  const a = new Allocation(id);
  a.user = user;
  a.allocator = allocator;
  a.strategy = strategy;
  a.capitalDeployed = BigInt.zero();
  a.strategyHighWaterMark = BigInt.zero();
  a.lastRebalanceAt = event.block.timestamp;
  return a;
}

// Phase 1 keeps the running `capitalDeployed` as the most recent event amount
// rather than a running sum. The Reputation Engine + dashboard derive the live
// total by summing AllocationCreated/Increased minus Decreased/Defunded events
// in their query layer. graph-ts 0.36's strict-null inference makes BigInt
// accumulation in mappings brittle (the operator-method `this` typing fights
// non-null entity getters), so we sidestep it for now. Phase 2 reintroduces
// running totals via @aggregation entities once we upgrade graph-ts.

export function handleAllocationCreated(event: AllocationCreated): void {
  const user = event.params.user as Bytes;
  const strategy = event.params.strategy as Bytes;
  const allocator = event.address; // AllocatorVault is per-allocator.

  getOrCreateUser(user, event.block.timestamp).save();
  getOrCreateAllocator(allocator, event.block.timestamp).save();
  getOrCreateStrategy(strategy, event.block.timestamp).save();

  const a = ensureAllocation(user, allocator, strategy, event);
  a.capitalDeployed = event.params.amount;
  a.lastRebalanceAt = event.block.timestamp;
  a.save();
}

export function handleAllocationIncreased(event: AllocationIncreased): void {
  const user = event.params.user as Bytes;
  const strategy = event.params.strategy as Bytes;
  const a = ensureAllocation(user, strategy, event.address, event);
  a.capitalDeployed = event.params.delta;
  a.lastRebalanceAt = event.block.timestamp;
  a.save();
}

export function handleAllocationDecreased(event: AllocationDecreased): void {
  const user = event.params.user as Bytes;
  const strategy = event.params.strategy as Bytes;
  const a = ensureAllocation(user, strategy, event.address, event);
  a.capitalDeployed = event.params.delta;
  a.lastRebalanceAt = event.block.timestamp;
  a.save();
}

export function handleStrategyDefunded(event: StrategyDefunded): void {
  const user = event.params.user as Bytes;
  const strategy = event.params.strategy as Bytes;
  const a = ensureAllocation(user, strategy, event.address, event);
  a.defundedAt = event.block.timestamp;
  a.defundReason = event.params.reason;
  a.save();

  const evt = new DefundEvent(logEventId(event));
  evt.user = user;
  evt.strategy = strategy;
  evt.reason = event.params.reason;
  evt.triggeredBy = event.params.triggeredBy as Bytes;
  evt.capitalRecovered = a.capitalDeployed;
  evt.timestamp = event.block.timestamp;
  evt.txHash = event.transaction.hash;
  evt.save();
}
