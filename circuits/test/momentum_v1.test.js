// Helios — momentum_v1 witness-generation tests.
//
// Phase 1 scaffold: validates the circuit compiles and accepts a
// well-formed valid witness. Full happy/invalid/boundary suite
// (Helios.md §9.3) lands as the constraint-5 signal logic firms up.

const path = require("node:path");
const test = require("node:test");
const assert = require("node:assert");
const snarkjs = require("snarkjs");
const { buildPoseidon } = require("circomlibjs");

const WASM = path.resolve(__dirname, "../build/momentum_v1/momentum_v1.wasm");
const UNIVERSE_SIZE = 8;

let poseidon;
let F;

test.before(async () => {
  poseidon = await buildPoseidon();
  F = poseidon.F;
});

// snarkjs leaks file handles via fastFile; the GC closes them after the
// test runner has marked the file complete, which throws an uncaughtException.
// Force a clean exit once all tests have actually finished.
test.after(() => {
  setImmediate(() => process.exit(0));
});

function asField(n) {
  return BigInt(n).toString();
}

function poseidonHash(inputs) {
  return F.toObject(poseidon(inputs.map((x) => BigInt(x)))).toString();
}

// Chained Poseidon: h0 = P(obs[0]); hi = P(h_{i-1}, obs[i]) for i in 1..15.
function chainedPoseidon(observations) {
  let h = poseidonHash([observations[0]]);
  for (let i = 1; i < observations.length; i++) {
    h = poseidonHash([h, observations[i]]);
  }
  return h;
}

function buildValidInput() {
  // Universe of 8 ERC-20 addresses (as field elements). Slot 0 = WKITE-ish.
  const universe = Array.from({ length: UNIVERSE_SIZE }, (_, i) => asField(0xaa00 + i));

  const asset_in = universe[0];
  const asset_out = universe[3];
  const amount_in = "1000000000000000000"; // 1.0 in 18-dec
  const max_position_size = "5000000000000000000"; // 5.0
  const max_slippage_bps = "50"; // 0.5%
  // min_amount_out >= amount_in * (10000 - 50) / 10000 = amount_in * 0.995
  const min_amount_out = "995000000000000000";
  const trade_direction = "1"; // long entry
  const allocator_address = asField(0xa11ca7);
  const nonce = "42";
  const block_window_start = "100";
  const block_window_end = "150"; // delta 50 ≤ 100

  // Monotonically rising bars: 1000, 1005, ..., 1075. Total 7.5% rise; with
  // signal_threshold of 100 bps the long-entry excess is positive.
  const price_observations = Array.from({ length: 16 }, (_, i) => asField(1000 + i * 5));
  const oracle_root = chainedPoseidon(price_observations);

  const declared_class = asField("0x1234");
  const trade_hash = poseidonHash([
    declared_class,
    asset_in,
    asset_out,
    amount_in,
    min_amount_out,
    trade_direction,
    allocator_address,
    nonce,
  ]);

  return {
    trade_hash,
    declared_class,
    asset_in,
    asset_out,
    amount_in,
    min_amount_out,
    trade_direction,
    allocator_address,
    nonce,
    block_window_start,
    block_window_end,
    asset_universe: universe,
    max_position_size,
    max_slippage_bps,
    position_state: "0",
    signal_threshold: "100", // 1.0% threshold
    price_observations,
    oracle_root,
    // Direction selector (one-hot) — long entry.
    is_long_entry: "1",
    is_short_entry: "0",
    is_exit: "0",
    // Exit reason — both 0 because is_exit == 0.
    is_signal_flip: "0",
    is_stop_loss: "0",
    stop_loss_price: "0",
  };
}

function buildValidExitInput() {
  // Same universe + bookkeeping as the long-entry case, but a falling price
  // series so the signal-flip exit predicate succeeds.
  const input = buildValidInput();
  // Reverse direction → exit (0); rebuild observations to fall by 7.5%.
  const falling = Array.from({ length: 16 }, (_, i) => asField(1075 - i * 5));
  input.price_observations = falling;
  input.oracle_root = chainedPoseidon(falling);
  input.trade_direction = "0";
  input.is_long_entry = "0";
  input.is_short_entry = "0";
  input.is_exit = "1";
  input.is_signal_flip = "1";
  input.is_stop_loss = "0";
  input.stop_loss_price = "0";
  // Recompute trade_hash for the new direction.
  input.trade_hash = poseidonHash([
    input.declared_class,
    input.asset_in,
    input.asset_out,
    input.amount_in,
    input.min_amount_out,
    input.trade_direction,
    input.allocator_address,
    input.nonce,
  ]);
  return input;
}

function buildValidStopLossInput() {
  // Long-position holder hits a stop loss: exit triggered by stop-loss reason.
  const input = buildValidInput();
  input.trade_direction = "0";
  input.is_long_entry = "0";
  input.is_short_entry = "0";
  input.is_exit = "1";
  input.is_signal_flip = "0";
  input.is_stop_loss = "1";
  // Last observation is 1075; set stop_loss_price >= 1075 so price_last <= stop.
  input.stop_loss_price = "1080";
  input.trade_hash = poseidonHash([
    input.declared_class,
    input.asset_in,
    input.asset_out,
    input.amount_in,
    input.min_amount_out,
    input.trade_direction,
    input.allocator_address,
    input.nonce,
  ]);
  return input;
}

test("momentum_v1: valid witness generates", async () => {
  const fs = require("node:fs");
  const out = "/tmp/helios_momentum_witness.wtns";
  const input = buildValidInput();
  await snarkjs.wtns.calculate(input, WASM, out);
  assert.ok(fs.statSync(out).size > 0, "witness file should be non-empty");
});

test("momentum_v1: amount_in over cap rejected", async () => {
  const input = buildValidInput();
  input.amount_in = "9999000000000000000000"; // way over max_position_size
  // Ensure the trade_hash still matches the (now bad) amount so the failure
  // is on the size constraint, not the hash binding.
  input.trade_hash = poseidonHash([
    input.declared_class,
    input.asset_in,
    input.asset_out,
    input.amount_in,
    input.min_amount_out,
    input.trade_direction,
    input.allocator_address,
    input.nonce,
  ]);
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_momentum_witness.wtns"));
});

test("momentum_v1: asset_in not in universe rejected", async () => {
  const input = buildValidInput();
  input.asset_in = asField(0xdead); // not in the universe
  input.trade_hash = poseidonHash([
    input.declared_class,
    input.asset_in,
    input.asset_out,
    input.amount_in,
    input.min_amount_out,
    input.trade_direction,
    input.allocator_address,
    input.nonce,
  ]);
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_momentum_witness.wtns"));
});

test("momentum_v1: window > 100 blocks rejected", async () => {
  const input = buildValidInput();
  input.block_window_end = "201"; // 201 - 100 = 101 > 100
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_momentum_witness.wtns"));
});

test("momentum_v1: trade_hash mismatch rejected", async () => {
  const input = buildValidInput();
  input.trade_hash = poseidonHash([1, 2, 3, 4, 5, 6, 7, 8]); // arbitrary wrong hash
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_momentum_witness.wtns"));
});

test("momentum_v1: oracle root mismatch rejected", async () => {
  const input = buildValidInput();
  input.oracle_root = "0"; // doesn't match the chained Poseidon of observations
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_momentum_witness.wtns"));
});

test("momentum_v1: long entry without sufficient momentum rejected", async () => {
  const input = buildValidInput();
  // Bump threshold above the 7.5% rise → long_excess_raw becomes negative.
  input.signal_threshold = "10000"; // 100%
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_momentum_witness.wtns"));
});

test("momentum_v1: direction-selector mismatch rejected", async () => {
  const input = buildValidInput();
  // trade_direction stays 1 (long), but the witness claims short.
  input.is_long_entry = "0";
  input.is_short_entry = "1";
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_momentum_witness.wtns"));
});

test("momentum_v1: exit (signal flip) accepted on falling prices", async () => {
  const fs = require("node:fs");
  const out = "/tmp/helios_momentum_witness.wtns";
  await snarkjs.wtns.calculate(buildValidExitInput(), WASM, out);
  assert.ok(fs.statSync(out).size > 0);
});

test("momentum_v1: exit (signal flip) rejected when prices still rising", async () => {
  const input = buildValidExitInput();
  // Override observations back to the rising series so the flip predicate fails.
  const rising = Array.from({ length: 16 }, (_, i) => asField(1000 + i * 5));
  input.price_observations = rising;
  input.oracle_root = chainedPoseidon(rising);
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_momentum_witness.wtns"));
});

test("momentum_v1: exit (stop loss) accepted when stop above last price", async () => {
  const fs = require("node:fs");
  const out = "/tmp/helios_momentum_witness.wtns";
  await snarkjs.wtns.calculate(buildValidStopLossInput(), WASM, out);
  assert.ok(fs.statSync(out).size > 0);
});

test("momentum_v1: exit (stop loss) rejected when stop below last price", async () => {
  const input = buildValidStopLossInput();
  // Last observation is 1075; pick a stop below that to force the predicate to fail.
  input.stop_loss_price = "500";
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_momentum_witness.wtns"));
});

test("momentum_v1: exit with neither flip nor stop-loss reason rejected", async () => {
  const input = buildValidInput();
  // Direction = exit but no reason flagged.
  input.trade_direction = "0";
  input.is_long_entry = "0";
  input.is_short_entry = "0";
  input.is_exit = "1";
  input.is_signal_flip = "0";
  input.is_stop_loss = "0";
  input.stop_loss_price = "0";
  input.trade_hash = poseidonHash([
    input.declared_class,
    input.asset_in,
    input.asset_out,
    input.amount_in,
    input.min_amount_out,
    input.trade_direction,
    input.allocator_address,
    input.nonce,
  ]);
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_momentum_witness.wtns"));
});
