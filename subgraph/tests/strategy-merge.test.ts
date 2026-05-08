// Phase 5 / WS6 — invariant test that confirms the subgraph keeps a
// single canonical Strategy entity per registry address even when
// trade events arrive from different chain datasources. This is the
// "single canonical entities keyed by address" choice in the Phase-5
// plan; the frontend (WS7) merges three Goldsky deployments by entity
// id and depends on the keying staying address-only.

import { Address, BigInt, Bytes, dataSource, ethereum } from "@graphprotocol/graph-ts";
import {
  afterAll,
  assert,
  beforeAll,
  clearStore,
  dataSourceMock,
  describe,
  newMockEvent,
  test,
} from "matchstick-as/assembly/index";
import { Strategy } from "../generated/schema";
import { TradeAttested } from "../generated/StrategyVault/StrategyVault";
import {
  handleTradeAttested,
  handleYieldRotationAttested,
} from "../src/strategy-vault";
import { YieldRotationAttested } from "../generated/StrategyVaultYieldRotation/StrategyVault";

const STRATEGY = Address.fromString("0x000000000000000000000000000000000000a11ce");
const ALLOCATOR = Address.fromString("0x000000000000000000000000000000000000b0b");
const ASSET_IN = Address.fromString("0x000000000000000000000000000000000000ca5h");
const ASSET_OUT = Address.fromString("0x000000000000000000000000000000000000beef");
const CLASS_HASH = Bytes.fromHexString(
  "0x4d4f4d454e54554d5f56310000000000000000000000000000000000000000aa",
);
const TRADE_HASH = Bytes.fromHexString(
  "0x1111111111111111111111111111111111111111111111111111111111111111",
);

function buildTradeAttested(network: string): TradeAttested {
  dataSourceMock.setNetwork(network);
  const ev = changetype<TradeAttested>(newMockEvent());
  ev.parameters = new Array<ethereum.EventParam>();
  ev.parameters.push(new ethereum.EventParam("strategy", ethereum.Value.fromAddress(STRATEGY)));
  ev.parameters.push(new ethereum.EventParam("allocator", ethereum.Value.fromAddress(ALLOCATOR)));
  ev.parameters.push(
    new ethereum.EventParam("tradeHash", ethereum.Value.fromFixedBytes(TRADE_HASH)),
  );
  ev.parameters.push(
    new ethereum.EventParam("declaredClass", ethereum.Value.fromFixedBytes(CLASS_HASH)),
  );
  ev.parameters.push(new ethereum.EventParam("assetIn", ethereum.Value.fromAddress(ASSET_IN)));
  ev.parameters.push(new ethereum.EventParam("assetOut", ethereum.Value.fromAddress(ASSET_OUT)));
  ev.parameters.push(
    new ethereum.EventParam("amountIn", ethereum.Value.fromUnsignedBigInt(BigInt.fromI32(100))),
  );
  ev.parameters.push(
    new ethereum.EventParam(
      "minAmountOut",
      ethereum.Value.fromUnsignedBigInt(BigInt.fromI32(99)),
    ),
  );
  ev.parameters.push(
    new ethereum.EventParam("direction", ethereum.Value.fromUnsignedBigInt(BigInt.fromI32(1))),
  );
  ev.parameters.push(
    new ethereum.EventParam(
      "blockWindowStart",
      ethereum.Value.fromUnsignedBigInt(BigInt.fromI32(1000)),
    ),
  );
  ev.parameters.push(
    new ethereum.EventParam(
      "blockWindowEnd",
      ethereum.Value.fromUnsignedBigInt(BigInt.fromI32(1010)),
    ),
  );
  return ev;
}

describe("WS6 — Strategy entity merges across chains", () => {
  beforeAll(() => {
    clearStore();
  });

  afterAll(() => {
    clearStore();
  });

  test("Kite + Base + Arbitrum trades collapse into a single Strategy row", () => {
    const id = Bytes.fromHexString(STRATEGY.toHexString());

    handleTradeAttested(buildTradeAttested("kite-ai-testnet"));
    handleTradeAttested(buildTradeAttested("base-sepolia"));
    handleTradeAttested(buildTradeAttested("arbitrum-sepolia"));

    // Exactly one Strategy row keyed by address.
    assert.entityCount("Strategy", 1);

    const s = Strategy.load(id);
    assert.assertNotNull(s);
    if (s == null) {
      return;
    }
    assert.i32Equals(s.totalAttestedTrades, 3);

    // executingChainIds gets all three, deduplicated.
    const chains = s.executingChainIds;
    assert.i32Equals(chains.length, 3);

    let sawKite = false;
    let sawBase = false;
    let sawArb = false;
    for (let i = 0; i < chains.length; i++) {
      const c = chains[i];
      if (c == 2368) sawKite = true;
      if (c == 84532) sawBase = true;
      if (c == 421614) sawArb = true;
    }
    assert.assertTrue(sawKite);
    assert.assertTrue(sawBase);
    assert.assertTrue(sawArb);
  });
});
