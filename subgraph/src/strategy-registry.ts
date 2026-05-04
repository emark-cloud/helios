import { Bytes } from "@graphprotocol/graph-ts";
import {
  StrategyRegistered,
  StrategyDeactivated,
  ReputationUpdated,
  ParamsRotated,
} from "../generated/StrategyRegistry/StrategyRegistry";
import { ParamsRotation } from "../generated/schema";
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

// Indexes the `ParamsRotated` event so the reputation engine
// (`services/reputation/src/reputation/goldsky.py::_QUERY_STRATEGY_STATE`)
// can read `Strategy.paramsRotations[0].timestamp` and reset the
// AgeScore + PerformanceScore window per §8.7. Without this handler, the
// engine's GraphQL query errors out and `tick_once` swallows it, so no
// scores update against a live Goldsky.
export function handleParamsRotated(event: ParamsRotated): void {
  const strategyId = event.params.strategyId as Bytes;
  // Touch the parent strategy so `paramsRotations` resolves cleanly.
  getOrCreateStrategy(strategyId, event.block.timestamp).save();

  const id = event.transaction.hash.concatI32(event.logIndex.toI32());
  const rotation = new ParamsRotation(id);
  rotation.strategy = strategyId;
  rotation.oldHash = event.params.oldHash;
  rotation.newHash = event.params.newHash;
  rotation.timestamp = event.block.timestamp;
  rotation.blockNumber = event.block.number;
  rotation.txHash = event.transaction.hash;
  rotation.save();
}
