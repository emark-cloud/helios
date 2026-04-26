import { Bytes } from "@graphprotocol/graph-ts";
import {
  MetaStrategySet,
  Deposited,
  AllocatorDelegated,
} from "../generated/UserVault/UserVault";
import { Deposit } from "../generated/schema";
import { getOrCreateAllocator, getOrCreateUser, logEventId } from "./helpers";

export function handleMetaStrategySet(event: MetaStrategySet): void {
  const user = getOrCreateUser(event.params.user as Bytes, event.block.timestamp);
  user.metaStrategyHash = event.params.metaStrategyHash;
  user.save();
}

export function handleDeposited(event: Deposited): void {
  const user = getOrCreateUser(event.params.user as Bytes, event.block.timestamp);
  user.save();

  const d = new Deposit(logEventId(event));
  d.user = user.id;
  d.asset = event.params.asset;
  d.amount = event.params.amount;
  d.timestamp = event.block.timestamp;
  d.txHash = event.transaction.hash;
  d.save();
}

export function handleAllocatorDelegated(event: AllocatorDelegated): void {
  const user = getOrCreateUser(event.params.user as Bytes, event.block.timestamp);
  const allocator = getOrCreateAllocator(
    event.params.allocator as Bytes,
    event.block.timestamp,
  );
  allocator.save();
  user.allocator = allocator.id;
  user.save();
}
