import { Bytes } from "@graphprotocol/graph-ts";
import {
  AllocatorRegistered,
  AllocatorDeactivated,
  AllocatorReputationUpdated,
  ReferenceBrandAssigned,
} from "../generated/AllocatorRegistry/AllocatorRegistry";
import { AllocatorReputationUpdate } from "../generated/schema";
import { getOrCreateAllocator, logEventId } from "./helpers";

export function handleAllocatorRegistered(event: AllocatorRegistered): void {
  const id = event.params.allocatorId as Bytes;
  const allocator = getOrCreateAllocator(id, event.block.timestamp);
  allocator.name = event.params.name;
  allocator.operator = event.params.operator;
  allocator.feeRateBps = event.params.feeRateBps;
  allocator.stakeAmount = event.params.stakeAmount;
  allocator.active = true;
  allocator.registeredAt = event.block.timestamp;
  allocator.save();
}

export function handleAllocatorDeactivated(event: AllocatorDeactivated): void {
  const id = event.params.allocatorId as Bytes;
  const allocator = getOrCreateAllocator(id, event.block.timestamp);
  allocator.active = false;
  allocator.save();
}

export function handleAllocatorReputationUpdated(event: AllocatorReputationUpdated): void {
  const id = event.params.allocatorId as Bytes;
  const allocator = getOrCreateAllocator(id, event.block.timestamp);
  allocator.currentReputation = event.params.newScore;
  allocator.save();

  // Phase 3 / WS5.B — append-only history. The aggregate
  // `Allocator.currentReputation` reflects the latest write; this
  // entity preserves the trajectory for the audit page + correlation
  // with the `AllocatorDecision` timeline.
  const update = new AllocatorReputationUpdate(logEventId(event));
  update.allocator = id;
  update.delta = event.params.delta;
  update.newScore = event.params.newScore;
  update.timestamp = event.block.timestamp;
  update.blockNumber = event.block.number;
  update.txHash = event.transaction.hash;
  update.save();
}

export function handleReferenceBrandAssigned(event: ReferenceBrandAssigned): void {
  const id = event.params.allocatorId as Bytes;
  const allocator = getOrCreateAllocator(id, event.block.timestamp);
  allocator.isReferenceBrand = true;
  allocator.save();
}
