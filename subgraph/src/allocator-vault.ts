import { BigInt, Bytes, crypto, ByteArray, ethereum } from "@graphprotocol/graph-ts";
import {
  AllocationCreated,
  AllocationIncreased,
  AllocationDecreased,
  StrategyDefunded,
} from "../generated/AllocatorVault/AllocatorVault";
import { Allocation, AllocatorDecision, DefundEvent } from "../generated/schema";
import {
  getOrCreateAllocator,
  getOrCreateDelegation,
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

// Phase 3 / WS5.B — emit a per-decision `AllocatorDecision` row for every
// allocator-driven capital move. The reputation engine windows these by
// timestamp for the allocator audit log; `/allocators/[name]` renders them
// chronologically. `kind` is the only categorical field — adding a new
// kind requires updating both the schema enum doc + frontend filter.
function emitDecision(
  event: ethereum.Event,
  allocator: Bytes,
  user: Bytes,
  strategy: Bytes,
  kind: string,
  amount: BigInt,
  reason: string | null,
): void {
  const d = new AllocatorDecision(logEventId(event));
  d.allocator = allocator;
  d.user = user;
  d.strategy = strategy;
  d.kind = kind;
  d.amount = amount;
  if (reason != null) d.reason = reason;
  d.timestamp = event.block.timestamp;
  d.blockNumber = event.block.number;
  d.txHash = event.transaction.hash;
  d.save();
}

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

  // WS5.B: upsert the (user, allocator) delegation. `since` is set on
  // first creation by `getOrCreateDelegation`; if the user previously
  // defunded and is re-allocating, clear `defundedAt` so the engine
  // counts them as actively retained.
  const delegation = getOrCreateDelegation(user, allocator, event.block.timestamp);
  delegation.capital = event.params.amount;
  delegation.defundedAt = null;
  delegation.save();

  emitDecision(event, allocator, user, strategy, "ALLOCATE", event.params.amount, null);
}

export function handleAllocationIncreased(event: AllocationIncreased): void {
  const user = event.params.user as Bytes;
  const strategy = event.params.strategy as Bytes;
  const allocator = event.address;
  const a = ensureAllocation(user, allocator, strategy, event);
  a.capitalDeployed = event.params.delta;
  a.lastRebalanceAt = event.block.timestamp;
  a.save();

  const delegation = getOrCreateDelegation(user, allocator, event.block.timestamp);
  delegation.capital = event.params.delta;
  delegation.save();

  emitDecision(
    event,
    allocator,
    user,
    strategy,
    "REBALANCE_INCREASE",
    event.params.delta,
    null,
  );
}

export function handleAllocationDecreased(event: AllocationDecreased): void {
  const user = event.params.user as Bytes;
  const strategy = event.params.strategy as Bytes;
  const allocator = event.address;
  const a = ensureAllocation(user, allocator, strategy, event);
  a.capitalDeployed = event.params.delta;
  a.lastRebalanceAt = event.block.timestamp;
  a.save();

  const delegation = getOrCreateDelegation(user, allocator, event.block.timestamp);
  delegation.capital = event.params.delta;
  delegation.save();

  emitDecision(
    event,
    allocator,
    user,
    strategy,
    "REBALANCE_DECREASE",
    event.params.delta,
    null,
  );
}

export function handleStrategyDefunded(event: StrategyDefunded): void {
  const user = event.params.user as Bytes;
  const strategy = event.params.strategy as Bytes;
  const allocator = event.address;
  const a = ensureAllocation(user, allocator, strategy, event);
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

  // WS5.B: mark the delegation defunded so retention math counts the
  // user as no longer delegated. A subsequent AllocationCreated for
  // the same (user, allocator) pair will clear `defundedAt`.
  const delegation = getOrCreateDelegation(user, allocator, event.block.timestamp);
  delegation.defundedAt = event.block.timestamp;
  delegation.save();

  emitDecision(event, allocator, user, strategy, "DEFUND", a.capitalDeployed, event.params.reason);
}
