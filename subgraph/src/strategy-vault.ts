import { BigInt, Bytes } from "@graphprotocol/graph-ts";
import {
  TradeAttested,
  NAVReported,
  Slashed,
} from "../generated/StrategyVault/StrategyVault";
import { Trade, NAVSnapshot } from "../generated/schema";
import { getOrCreateAllocator, getOrCreateStrategy, logEventId, PHASE1_CHAIN_ID } from "./helpers";

export function handleTradeAttested(event: TradeAttested): void {
  // The verify call has already passed if this event fires (StrategyVault
  // reverts otherwise), so `proofValid` is unconditionally true at this
  // shouldn't-revert observation point. Any aborted attestation never emits.
  const trade = new Trade(logEventId(event));
  trade.strategy = event.params.strategy;
  trade.allocator = event.params.allocator;
  trade.declaredClass = (event.params.declaredClass as Bytes).toHexString();
  trade.tradeHash = event.params.tradeHash;
  trade.proofValid = true;
  trade.assetIn = event.params.assetIn;
  trade.assetOut = event.params.assetOut;
  trade.amountIn = event.params.amountIn;
  trade.minAmountOut = event.params.minAmountOut;
  trade.direction = event.params.direction;
  // uint64 event params arrive as BigInt from graph-codegen.
  trade.blockWindowStart = event.params.blockWindowStart;
  trade.blockWindowEnd = event.params.blockWindowEnd;
  trade.timestamp = event.block.timestamp;
  trade.txHash = event.transaction.hash;
  trade.chainId = PHASE1_CHAIN_ID;
  trade.save();

  // Make sure parent entities exist so `@derivedFrom` lookups work.
  const strategy = getOrCreateStrategy(event.params.strategy as Bytes, event.block.timestamp);
  strategy.totalAttestedTrades = strategy.totalAttestedTrades + 1;
  strategy.save();
  getOrCreateAllocator(event.params.allocator as Bytes, event.block.timestamp).save();
}

export function handleNAVReported(event: NAVReported): void {
  const snap = new NAVSnapshot(logEventId(event));
  snap.strategy = event.params.strategy;
  snap.totalNAV = event.params.totalNAV;
  snap.timestamp = event.params.timestamp;
  snap.save();

  // Touch the parent so `@derivedFrom` reverse links populate before the
  // strategy is independently registered (rare but possible under reorgs).
  getOrCreateStrategy(event.params.strategy as Bytes, event.block.timestamp).save();
}

export function handleSlashed(event: Slashed): void {
  // Slashing in Phase 1 is recorded on the registry side via stake delta; here
  // we only ensure the strategy is touched so subsequent reads see the event
  // ordering correctly. A dedicated SlashEvent entity lands in Phase 2 if the
  // dashboard surfaces a slashing timeline.
  getOrCreateStrategy(event.params.strategy as Bytes, event.block.timestamp).save();
}
