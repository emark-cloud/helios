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

  // Price observations: 16 monotonically rising bars (consistent with momentum).
  const price_observations = Array.from({ length: 16 }, (_, i) => asField(1000 + i * 5));
  // oracle_root = Poseidon(observations) — matches the scaffold's binding.
  const oracle_root = poseidonHash(price_observations);

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
    signal_threshold: "10",
    price_observations,
    oracle_root,
  };
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
