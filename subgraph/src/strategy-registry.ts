import { Bytes } from "@graphprotocol/graph-ts";
import {
  StrategyRegistered,
  StrategyDeactivated,
  ReputationUpdated,
  ParamsRotated,
  MarketAllowlistRootSet,
  ParamsHashCommitted,
  ParamsRotationInitiated,
  ParamsRotationCancelled,
} from "../generated/StrategyRegistry/StrategyRegistry";
import {
  MarketAllowlistRoot,
  ParamsCommitment,
  ParamsRotation,
  ParamsRotationCancellation,
  ParamsRotationProposal,
} from "../generated/schema";
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

// `MarketAllowlistRootSet(declaredClass, root)` — class-level allowlist
// roots used by yield_rotation_v1 trades. The audit page renders these
// so operators can prove the allowlist witness used at trade-time
// matches the registry-canonical value.
export function handleMarketAllowlistRootSet(event: MarketAllowlistRootSet): void {
  const id = event.transaction.hash.concatI32(event.logIndex.toI32());
  const row = new MarketAllowlistRoot(id);
  row.declaredClass = event.params.declaredClass;
  row.root = event.params.root;
  row.timestamp = event.block.timestamp;
  row.blockNumber = event.block.number;
  row.txHash = event.transaction.hash;
  row.save();
}

// `ParamsHashCommitted(strategyId, paramsHash)` — append-only history
// of `paramsHash` commits per strategy. The most-recent row is the
// canonical hash circuit proofs must bind through `trade_hash`.
export function handleParamsHashCommitted(event: ParamsHashCommitted): void {
  const strategyId = event.params.strategyId as Bytes;
  getOrCreateStrategy(strategyId, event.block.timestamp).save();

  const id = event.transaction.hash.concatI32(event.logIndex.toI32());
  const row = new ParamsCommitment(id);
  row.strategy = strategyId;
  row.paramsHash = event.params.paramsHash;
  row.timestamp = event.block.timestamp;
  row.blockNumber = event.block.number;
  row.txHash = event.transaction.hash;
  row.save();
}

// `ParamsRotationInitiated(strategyId, oldHash, newHash, unlockAt)` —
// opens a rotation cooldown window. UI uses `unlockAt` to render the
// countdown until either a `ParamsRotated` (completion) or
// `ParamsRotationCancelled` event closes the window.
export function handleParamsRotationInitiated(event: ParamsRotationInitiated): void {
  const strategyId = event.params.strategyId as Bytes;
  getOrCreateStrategy(strategyId, event.block.timestamp).save();

  const id = event.transaction.hash.concatI32(event.logIndex.toI32());
  const row = new ParamsRotationProposal(id);
  row.strategy = strategyId;
  row.oldHash = event.params.oldHash;
  row.newHash = event.params.newHash;
  row.unlockAt = event.params.unlockAt;
  row.timestamp = event.block.timestamp;
  row.blockNumber = event.block.number;
  row.txHash = event.transaction.hash;
  row.save();
}

// `ParamsRotationCancelled(strategyId, cancelledNewHash)` — pairs with
// a preceding `ParamsRotationProposal` row by `(strategy, newHash)`.
export function handleParamsRotationCancelled(event: ParamsRotationCancelled): void {
  const strategyId = event.params.strategyId as Bytes;
  getOrCreateStrategy(strategyId, event.block.timestamp).save();

  const id = event.transaction.hash.concatI32(event.logIndex.toI32());
  const row = new ParamsRotationCancellation(id);
  row.strategy = strategyId;
  row.cancelledNewHash = event.params.cancelledNewHash;
  row.timestamp = event.block.timestamp;
  row.blockNumber = event.block.number;
  row.txHash = event.transaction.hash;
  row.save();
}
