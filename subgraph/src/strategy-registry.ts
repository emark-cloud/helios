import { Bytes } from "@graphprotocol/graph-ts";
import {
  StrategyRegistered,
  StrategyDeactivated,
  ReputationUpdated,
} from "../generated/StrategyRegistry/StrategyRegistry";
import { getOrCreateStrategy, PHASE1_CHAIN_ID } from "./helpers";

export function handleStrategyRegistered(event: StrategyRegistered): void {
  const id = event.params.strategyId as Bytes;
  const strategy = getOrCreateStrategy(id, event.block.timestamp);
  strategy.operator = event.params.operator;
  // declaredClass is the bytes32 class id (e.g. keccak("momentum_v1")). Stored as hex
  // so the frontend can match it against the human-readable class registry.
  strategy.declaredClass = (event.params.declaredClass as Bytes).toHexString();
  strategy.stakeAmount = event.params.stakeAmount;
  strategy.active = true;
  strategy.registeredAt = event.block.timestamp;
  // chainId is set when StrategyVault first emits NAVReported / TradeAttested for a
  // multi-chain strategy. Phase 1 is single-chain so default to Kite testnet.
  strategy.chainId = PHASE1_CHAIN_ID;
  strategy.save();
}

export function handleStrategyDeactivated(event: StrategyDeactivated): void {
  const id = event.params.strategyId as Bytes;
  const strategy = getOrCreateStrategy(id, event.block.timestamp);
  strategy.active = false;
  strategy.save();
}

export function handleStrategyReputationUpdated(event: ReputationUpdated): void {
  const id = event.params.strategyId as Bytes;
  const strategy = getOrCreateStrategy(id, event.block.timestamp);
  strategy.currentReputation = event.params.newScore;
  strategy.save();
}
