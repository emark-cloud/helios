// Helios — momentum_v1 witness-generation tests.
//
// Validates the v2 circuit schema (14 public inputs, params_hash binding,
// strategy_vault binding, asset indices instead of address membership).

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

// snarkjs leaks file handles via fastFile; force a clean exit once done.
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

function paramsHashOf({ max_position_size, max_slippage_bps, signal_threshold, stop_loss_price }) {
  return poseidonHash([max_position_size, max_slippage_bps, signal_threshold, stop_loss_price]);
}

function tradeHashOf(input) {
  return poseidonHash([
    input.strategy_vault,
    input.declared_class,
    input.params_hash,
    input.allocator_address,
    input.asset_in_idx,
    input.asset_out_idx,
    input.amount_in,
    input.min_amount_out,
    input.trade_direction,
    input.nonce,
  ]);
}

function buildValidInput() {
  const max_position_size = "5000000000000000000"; // 5.0
  const max_slippage_bps = "50"; // 0.5%
  const signal_threshold = "100"; // 1.0%
  const stop_loss_price = "0";
  const params_hash = paramsHashOf({
    max_position_size,
    max_slippage_bps,
    signal_threshold,
    stop_loss_price,
  });

  // Monotonically rising bars: 1000, 1005, ..., 1075. Total 7.5% rise.
  const price_observations = Array.from({ length: 16 }, (_, i) => asField(1000 + i * 5));
  const oracle_root = chainedPoseidon(price_observations);

  const base = {
    declared_class: asField("0x1234"),
    strategy_vault: asField("0xbeef00"),
    params_hash,
    allocator_address: asField("0xa11ca7"),
    asset_in_idx: "0",
    asset_out_idx: "3",
    amount_in: "1000000000000000000",
    // amount_in * (10000 - 50) / 10000 = 0.995 * 1e18.
    min_amount_out: "995000000000000000",
    trade_direction: "1", // long entry
    nonce: "42",
    block_window_start: "100",
    block_window_end: "150",
    oracle_root,
    max_position_size,
    max_slippage_bps,
    signal_threshold,
    stop_loss_price,
    price_observations,
    is_long_entry: "1",
    is_short_entry: "0",
    is_exit: "0",
    is_signal_flip: "0",
    is_stop_loss: "0",
    // HIGH #11 — was_long is private. 1 = unwinding a long; 0 = short.
    // Bound only when is_signal_flip = 1; default to 1 here (the long-side
    // case used by the existing exit tests).
    was_long: "1",
  };
  base.trade_hash = tradeHashOf(base);
  return base;
}

function buildValidExitInput() {
  const input = buildValidInput();
  // Falling series → signal-flip exit.
  const falling = Array.from({ length: 16 }, (_, i) => asField(1075 - i * 5));
  input.price_observations = falling;
  input.oracle_root = chainedPoseidon(falling);
  input.trade_direction = "0";
  input.is_long_entry = "0";
  input.is_short_entry = "0";
  input.is_exit = "1";
  input.is_signal_flip = "1";
  input.is_stop_loss = "0";
  input.trade_hash = tradeHashOf(input);
  return input;
}

function buildValidStopLossInput() {
  const input = buildValidInput();
  // Long-position holder hits a stop loss: exit triggered by stop-loss reason.
  input.trade_direction = "0";
  input.is_long_entry = "0";
  input.is_short_entry = "0";
  input.is_exit = "1";
  input.is_signal_flip = "0";
  input.is_stop_loss = "1";
  // Last observation is 1075; stop_loss_price >= 1075 satisfies (stop - last) >= 0.
  input.stop_loss_price = "1080";
  input.params_hash = paramsHashOf(input);
  input.trade_hash = tradeHashOf(input);
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
  input.trade_hash = tradeHashOf(input);
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_momentum_witness.wtns"));
});

test("momentum_v1: amount_in == 0 rejected", async () => {
  // Constraint 0: amount_in > 0. Mirrors yield_rotation_v1 Constraint 7.
  const input = buildValidInput();
  input.amount_in = "0";
  input.min_amount_out = "0";
  input.trade_hash = tradeHashOf(input);
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_momentum_witness.wtns"));
});

test("momentum_v1: asset_in_idx out of range rejected", async () => {
  const input = buildValidInput();
  input.asset_in_idx = String(UNIVERSE_SIZE); // == UNIVERSE_SIZE → must fail (< check)
  input.trade_hash = tradeHashOf(input);
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_momentum_witness.wtns"));
});

test("momentum_v1: window > 100 blocks rejected", async () => {
  const input = buildValidInput();
  input.block_window_end = "201"; // 201 - 100 = 101 > 100
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_momentum_witness.wtns"));
});

test("momentum_v1: trade_hash mismatch rejected", async () => {
  const input = buildValidInput();
  input.trade_hash = poseidonHash([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]); // arbitrary wrong hash
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_momentum_witness.wtns"));
});

test("momentum_v1: params_hash mismatch rejected", async () => {
  const input = buildValidInput();
  // Tamper a private parameter without re-deriving params_hash.
  input.max_position_size = "9999000000000000000";
  // trade_hash is over public fields — params_hash itself is public so the
  // trade_hash recomputation isn't needed here; the constraint failure is
  // on the params Poseidon equality.
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_momentum_witness.wtns"));
});

test("momentum_v1: oracle root mismatch rejected", async () => {
  const input = buildValidInput();
  input.oracle_root = "0"; // doesn't match chained Poseidon of observations
  input.trade_hash = tradeHashOf(input);
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_momentum_witness.wtns"));
});

test("momentum_v1: max_slippage_bps over 10000 rejected", async () => {
  const input = buildValidInput();
  input.max_slippage_bps = "20000";
  input.params_hash = paramsHashOf(input);
  input.trade_hash = tradeHashOf(input);
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_momentum_witness.wtns"));
});

test("momentum_v1: long entry without sufficient momentum rejected", async () => {
  const input = buildValidInput();
  // Bump threshold above the 7.5% rise → long_excess_raw becomes negative.
  input.signal_threshold = "10000"; // 100%
  input.params_hash = paramsHashOf(input);
  input.trade_hash = tradeHashOf(input);
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
  const rising = Array.from({ length: 16 }, (_, i) => asField(1000 + i * 5));
  input.price_observations = rising;
  input.oracle_root = chainedPoseidon(rising);
  input.trade_hash = tradeHashOf(input);
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
  input.params_hash = paramsHashOf(input);
  input.trade_hash = tradeHashOf(input);
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_momentum_witness.wtns"));
});

test("momentum_v1: exit with neither flip nor stop-loss reason rejected", async () => {
  const input = buildValidInput();
  input.trade_direction = "0";
  input.is_long_entry = "0";
  input.is_short_entry = "0";
  input.is_exit = "1";
  input.is_signal_flip = "0";
  input.is_stop_loss = "0";
  input.stop_loss_price = "0";
  input.trade_hash = tradeHashOf(input);
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_momentum_witness.wtns"));
});

// HIGH #11 — short-side signal-flip exit must verify on rising prices.
test("momentum_v1: short signal-flip exit accepted on rising prices", async () => {
  const fs = require("node:fs");
  const input = buildValidInput();
  // Rising series — would trigger a flip exit for a SHORT position.
  const rising = Array.from({ length: 16 }, (_, i) => asField(1000 + i * 5));
  input.price_observations = rising;
  input.oracle_root = chainedPoseidon(rising);
  input.trade_direction = "0";
  input.is_long_entry = "0";
  input.is_short_entry = "0";
  input.is_exit = "1";
  input.is_signal_flip = "1";
  input.is_stop_loss = "0";
  input.was_long = "0"; // unwinding a short
  input.trade_hash = tradeHashOf(input);
  const out = "/tmp/helios_momentum_witness.wtns";
  await snarkjs.wtns.calculate(input, WASM, out);
  assert.ok(fs.statSync(out).size > 0);
});

// HIGH #11 — and the inverse: claiming a long flip while the witness
// recorded a short (was_long=0) must fail when only down-delta would
// satisfy the threshold.
test("momentum_v1: signal-flip with wrong was_long rejected", async () => {
  const input = buildValidExitInput(); // falling series, was_long=1 by default
  input.was_long = "0"; // claim short, but the falling-prices delta only justifies long-flip
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_momentum_witness.wtns"));
});

// HIGH #12 — self-swap (asset_in_idx == asset_out_idx) must fail.
test("momentum_v1: self-swap rejected", async () => {
  const input = buildValidInput();
  input.asset_in_idx = "3";
  input.asset_out_idx = "3";
  input.trade_hash = tradeHashOf(input);
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_momentum_witness.wtns"));
});

// docs/circuit-specs.md §1.6 gap — bit-width-edge: amount_in,
// min_amount_out, max_position_size all at exactly 2^128 − 1 must
// still satisfy Num2Bits(128) (Constraint A.2 / B.2). max_slippage_bps
// pinned to 0 so the slippage bound collapses to min_amount_out ≥
// amount_in. Sub-160-bit slipRhs (~142 bits) keeps Constraint 2 happy.
test("momentum_v1: amounts at 2^128 − 1 boundary accepted", async () => {
  const fs = require("node:fs");
  const out = "/tmp/helios_momentum_witness.wtns";
  const max128 = ((1n << 128n) - 1n).toString();
  const input = buildValidInput();
  input.max_slippage_bps = "0";
  input.max_position_size = max128;
  input.amount_in = max128;
  input.min_amount_out = max128;
  input.params_hash = paramsHashOf(input);
  input.trade_hash = tradeHashOf(input);
  await snarkjs.wtns.calculate(input, WASM, out);
  assert.ok(fs.statSync(out).size > 0);
});

// docs/circuit-specs.md §1.6 gap — short-entry happy path mirrors the
// long-entry fixture but on a falling-series witness. Exercises
// Constraint 4 short branch end-to-end.
test("momentum_v1: valid short entry on falling prices", async () => {
  const fs = require("node:fs");
  const out = "/tmp/helios_momentum_witness.wtns";
  const input = buildValidInput();
  const falling = Array.from({ length: 16 }, (_, i) => asField(1075 - i * 5));
  input.price_observations = falling;
  input.oracle_root = chainedPoseidon(falling);
  input.trade_direction = "2";
  input.is_long_entry = "0";
  input.is_short_entry = "1";
  input.is_exit = "0";
  input.trade_hash = tradeHashOf(input);
  await snarkjs.wtns.calculate(input, WASM, out);
  assert.ok(fs.statSync(out).size > 0);
});
