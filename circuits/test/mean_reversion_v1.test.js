// Helios — mean_reversion_v1 witness-generation tests.
//
// Validates the v2 schema (14 public inputs, params_hash binding,
// strategy_vault binding, asset indices). Signal logic is inverted vs
// momentum: long on N-sigma DOWN, short on N-sigma UP, exit on mean
// re-cross or stop-loss.

const path = require("node:path");
const test = require("node:test");
const assert = require("node:assert");
const snarkjs = require("snarkjs");
const { buildPoseidon } = require("circomlibjs");

const WASM = path.resolve(__dirname, "../build/mean_reversion_v1/mean_reversion_v1.wasm");
const UNIVERSE_SIZE = 8;

let poseidon;
let F;

test.before(async () => {
  poseidon = await buildPoseidon();
  F = poseidon.F;
});

test.after(() => {
  setImmediate(() => process.exit(0));
});

function asField(n) {
  return BigInt(n).toString();
}

function poseidonHash(inputs) {
  return F.toObject(poseidon(inputs.map((x) => BigInt(x)))).toString();
}

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

// 15 bars at `base`, last bar at `outlier`. Returns price observations as
// strings. With base=1000 and outlier=700 (or 1300), the last bar is ~3.87σ
// from the mean, comfortably above a 2.00σ (signal_threshold = 200) gate.
function buildSeries(base, outlier) {
  const prices = Array(15).fill(asField(base));
  prices.push(asField(outlier));
  return prices;
}

// Variance-rich series: 8 bars at 800, 7 bars at 1200, last bar = `last`.
// The early-bar oscillation gives the stddev real heft (~205 in dev16
// terms), so a `last` close to the cluster mean (1040) sits at sub-σ
// distance — the regime where mean-re-cross and "insufficient deviation"
// cases live. With last=1040 the series is exactly at mean.
function buildVarianceSeries(last) {
  const prices = [];
  for (let i = 0; i < 8; i++) prices.push(asField(800));
  for (let i = 0; i < 7; i++) prices.push(asField(1200));
  prices.push(asField(last));
  return prices;
}

function buildLongEntryInput() {
  const max_position_size = "5000000000000000000";
  const max_slippage_bps = "50";
  const signal_threshold = "200"; // 2.00σ
  const stop_loss_price = "0";
  const params_hash = paramsHashOf({
    max_position_size,
    max_slippage_bps,
    signal_threshold,
    stop_loss_price,
  });

  // Long entry: last bar far below the mean.
  const price_observations = buildSeries(1000, 700);
  const oracle_root = chainedPoseidon(price_observations);

  const base = {
    declared_class: asField("0x5678"),
    strategy_vault: asField("0xbeef00"),
    params_hash,
    allocator_address: asField("0xa11ca7"),
    asset_in_idx: "0",
    asset_out_idx: "3",
    amount_in: "1000000000000000000",
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
  };
  base.trade_hash = tradeHashOf(base);
  return base;
}

function buildShortEntryInput() {
  const input = buildLongEntryInput();
  // Short entry: last bar far above the mean.
  input.price_observations = buildSeries(1000, 1300);
  input.oracle_root = chainedPoseidon(input.price_observations);
  input.trade_direction = "2"; // short entry
  input.is_long_entry = "0";
  input.is_short_entry = "1";
  input.trade_hash = tradeHashOf(input);
  return input;
}

function buildExitFlipInput() {
  const input = buildLongEntryInput();
  // Mean re-cross: variance-rich oscillation + last bar exactly at the
  // 1040 cluster mean ⇒ dev_last_sq = 0, lhs = 0 ≤ rhs ⇒ flip excess ≥ 0.
  input.price_observations = buildVarianceSeries(1040);
  input.oracle_root = chainedPoseidon(input.price_observations);
  input.trade_direction = "0";
  input.is_long_entry = "0";
  input.is_short_entry = "0";
  input.is_exit = "1";
  input.is_signal_flip = "1";
  input.is_stop_loss = "0";
  input.trade_hash = tradeHashOf(input);
  return input;
}

function buildExitStopLossInput() {
  const input = buildLongEntryInput();
  // Stop loss exit: last price is below stop_loss_price.
  input.price_observations = buildSeries(1000, 700);
  input.oracle_root = chainedPoseidon(input.price_observations);
  input.trade_direction = "0";
  input.is_long_entry = "0";
  input.is_short_entry = "0";
  input.is_exit = "1";
  input.is_signal_flip = "0";
  input.is_stop_loss = "1";
  // stop ≥ last_price ⇒ stop_loss_price = 800 satisfies (800 ≥ 700).
  input.stop_loss_price = "800";
  input.params_hash = paramsHashOf(input);
  input.trade_hash = tradeHashOf(input);
  return input;
}

test("mean_reversion_v1: valid long entry on N-sigma down", async () => {
  const fs = require("node:fs");
  const out = "/tmp/helios_meanrev_witness.wtns";
  await snarkjs.wtns.calculate(buildLongEntryInput(), WASM, out);
  assert.ok(fs.statSync(out).size > 0);
});

test("mean_reversion_v1: valid short entry on N-sigma up", async () => {
  const fs = require("node:fs");
  const out = "/tmp/helios_meanrev_witness.wtns";
  await snarkjs.wtns.calculate(buildShortEntryInput(), WASM, out);
  assert.ok(fs.statSync(out).size > 0);
});

test("mean_reversion_v1: valid exit on mean re-cross", async () => {
  const fs = require("node:fs");
  const out = "/tmp/helios_meanrev_witness.wtns";
  await snarkjs.wtns.calculate(buildExitFlipInput(), WASM, out);
  assert.ok(fs.statSync(out).size > 0);
});

test("mean_reversion_v1: valid exit on stop-loss", async () => {
  const fs = require("node:fs");
  const out = "/tmp/helios_meanrev_witness.wtns";
  await snarkjs.wtns.calculate(buildExitStopLossInput(), WASM, out);
  assert.ok(fs.statSync(out).size > 0);
});

test("mean_reversion_v1: amount_in over cap rejected", async () => {
  const input = buildLongEntryInput();
  input.amount_in = "9999000000000000000000";
  input.trade_hash = tradeHashOf(input);
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_meanrev_witness.wtns"));
});

test("mean_reversion_v1: amount_in == 0 rejected", async () => {
  // Constraint 0: amount_in > 0. Mirrors yield_rotation_v1 Constraint 7.
  const input = buildLongEntryInput();
  input.amount_in = "0";
  input.min_amount_out = "0";
  input.trade_hash = tradeHashOf(input);
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_meanrev_witness.wtns"));
});

test("mean_reversion_v1: asset_in_idx out of range rejected", async () => {
  const input = buildLongEntryInput();
  input.asset_in_idx = String(UNIVERSE_SIZE);
  input.trade_hash = tradeHashOf(input);
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_meanrev_witness.wtns"));
});

test("mean_reversion_v1: long entry with insufficient deviation rejected", async () => {
  const input = buildLongEntryInput();
  // Variance-rich early bars (~205 stddev in dev16 terms); last bar at 700
  // sits ~1.31σ below mean — within the 2.00σ threshold ⇒ entry rejected.
  input.price_observations = buildVarianceSeries(700);
  input.oracle_root = chainedPoseidon(input.price_observations);
  input.trade_hash = tradeHashOf(input);
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_meanrev_witness.wtns"));
});

test("mean_reversion_v1: long entry with wrong sign rejected", async () => {
  const input = buildLongEntryInput();
  // Price ABOVE mean — claiming long entry should reject on the sign check.
  input.price_observations = buildSeries(1000, 1300);
  input.oracle_root = chainedPoseidon(input.price_observations);
  input.trade_hash = tradeHashOf(input);
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_meanrev_witness.wtns"));
});

test("mean_reversion_v1: short entry with wrong sign rejected", async () => {
  const input = buildShortEntryInput();
  // Price BELOW mean — claiming short entry should reject on the sign check.
  input.price_observations = buildSeries(1000, 700);
  input.oracle_root = chainedPoseidon(input.price_observations);
  input.trade_hash = tradeHashOf(input);
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_meanrev_witness.wtns"));
});

test("mean_reversion_v1: window > 100 blocks rejected", async () => {
  const input = buildLongEntryInput();
  input.block_window_end = "201";
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_meanrev_witness.wtns"));
});

test("mean_reversion_v1: trade_hash mismatch rejected", async () => {
  const input = buildLongEntryInput();
  input.trade_hash = poseidonHash([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_meanrev_witness.wtns"));
});

test("mean_reversion_v1: params_hash mismatch rejected", async () => {
  const input = buildLongEntryInput();
  input.max_position_size = "9999000000000000000";
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_meanrev_witness.wtns"));
});

test("mean_reversion_v1: oracle root mismatch rejected", async () => {
  const input = buildLongEntryInput();
  input.oracle_root = "0";
  input.trade_hash = tradeHashOf(input);
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_meanrev_witness.wtns"));
});

test("mean_reversion_v1: max_slippage_bps over 10000 rejected", async () => {
  const input = buildLongEntryInput();
  input.max_slippage_bps = "20000";
  input.params_hash = paramsHashOf(input);
  input.trade_hash = tradeHashOf(input);
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_meanrev_witness.wtns"));
});

test("mean_reversion_v1: direction-selector mismatch rejected", async () => {
  const input = buildLongEntryInput();
  input.is_long_entry = "0";
  input.is_short_entry = "1"; // claims short while trade_direction = 1 (long)
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_meanrev_witness.wtns"));
});

test("mean_reversion_v1: exit (signal flip) rejected when deviation still beyond threshold", async () => {
  const input = buildExitFlipInput();
  // Restore the wide deviation: still N-sigma off the mean ⇒ flip excess negative.
  input.price_observations = buildSeries(1000, 700);
  input.oracle_root = chainedPoseidon(input.price_observations);
  input.trade_hash = tradeHashOf(input);
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_meanrev_witness.wtns"));
});

test("mean_reversion_v1: exit (stop loss) rejected when stop below last price", async () => {
  const input = buildExitStopLossInput();
  // Last bar = 700; stop = 500 < 700 ⇒ sl_excess negative.
  input.stop_loss_price = "500";
  input.params_hash = paramsHashOf(input);
  input.trade_hash = tradeHashOf(input);
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_meanrev_witness.wtns"));
});

test("mean_reversion_v1: exit with neither flip nor stop-loss reason rejected", async () => {
  const input = buildLongEntryInput();
  input.trade_direction = "0";
  input.is_long_entry = "0";
  input.is_short_entry = "0";
  input.is_exit = "1";
  input.is_signal_flip = "0";
  input.is_stop_loss = "0";
  input.stop_loss_price = "0";
  input.trade_hash = tradeHashOf(input);
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_meanrev_witness.wtns"));
});

// HIGH #12 — self-swap (asset_in_idx == asset_out_idx) must fail.
test("mean_reversion_v1: self-swap rejected", async () => {
  const input = buildLongEntryInput();
  input.asset_in_idx = "3";
  input.asset_out_idx = "3";
  input.trade_hash = tradeHashOf(input);
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_meanrev_witness.wtns"));
});

// docs/circuit-specs.md §2.6 gap — bit-width-edge: amount_in /
// min_amount_out / max_position_size at exactly 2^128 − 1 still
// satisfy Num2Bits(128) (Constraint A.2 / B.2 reused from §1.3).
// max_slippage_bps pinned to 0 collapses Constraint 2 to
// min_amount_out ≥ amount_in.
test("mean_reversion_v1: amounts at 2^128 − 1 boundary accepted", async () => {
  const fs = require("node:fs");
  const out = "/tmp/helios_meanrev_witness.wtns";
  const max128 = ((1n << 128n) - 1n).toString();
  const input = buildLongEntryInput();
  input.max_slippage_bps = "0";
  input.max_position_size = max128;
  input.amount_in = max128;
  input.min_amount_out = max128;
  input.params_hash = paramsHashOf(input);
  input.trade_hash = tradeHashOf(input);
  await snarkjs.wtns.calculate(input, WASM, out);
  assert.ok(fs.statSync(out).size > 0);
});

// docs/circuit-specs.md §2.6 gap — claiming both is_signal_flip = 1 and
// is_stop_loss = 1 simultaneously must fail Constraint 6's
// `is_exit === is_signal_flip + is_stop_loss` (1 ≠ 2). Exit-reason
// algebra forecloses double-counting.
test("mean_reversion_v1: is_signal_flip + is_stop_loss > 1 rejected", async () => {
  const input = buildExitFlipInput();
  input.is_signal_flip = "1";
  input.is_stop_loss = "1";
  // Last bar = 1040; stop above last keeps the stop-loss raw excess
  // ≥ 0 so the failure is the exit-reason sum, not the stop predicate.
  input.stop_loss_price = "1100";
  input.params_hash = paramsHashOf(input);
  input.trade_hash = tradeHashOf(input);
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_meanrev_witness.wtns"));
});
