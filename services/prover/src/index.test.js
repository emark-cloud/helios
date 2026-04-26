// Helios prover — service integration tests.
//
// Round-trips a real momentum_v1 proof through POST /prove and verifies it
// off-chain via snarkjs.groth16.verify against the same verification key the
// MomentumV1Verifier.sol scaffold was generated from. On-chain verification
// is covered by contracts/test/MomentumV1Verifier.t.sol — re-asserting it
// here with anvil would be redundant since the off-chain vkey and the
// on-chain Verifier are deterministically derived from the same .zkey.

import path from "node:path";
import url from "node:url";
import fs from "node:fs/promises";
import test from "node:test";
import assert from "node:assert/strict";
import request from "supertest";
import * as snarkjs from "snarkjs";
import { buildPoseidon } from "circomlibjs";
import { createApp } from "./index.js";

const __dirname = path.dirname(url.fileURLToPath(import.meta.url));
const CIRCUITS_DIR = path.resolve(__dirname, "..", "..", "..", "circuits", "build");
const VKEY_PATH = path.join(CIRCUITS_DIR, "momentum_v1", "verification_key.json");
const UNIVERSE_SIZE = 8;

let poseidon;
let F;

test.before(async () => {
  poseidon = await buildPoseidon();
  F = poseidon.F;
});

// snarkjs leaks file handles via fastFile; force a clean exit once tests finish.
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

// Mirrors circuits/test/momentum_v1.test.js::buildValidInput. Kept colocated
// here (rather than imported) so the prover service stays a leaf node — no
// path-back into the circuits workspace at runtime.
function buildValidMomentumInput() {
  const universe = Array.from({ length: UNIVERSE_SIZE }, (_, i) => asField(0xaa00 + i));
  const asset_in = universe[0];
  const asset_out = universe[3];
  const amount_in = "1000000000000000000";
  const max_position_size = "5000000000000000000";
  const max_slippage_bps = "50";
  const min_amount_out = "995000000000000000";
  const trade_direction = "1";
  const allocator_address = asField(0xa11ca7);
  const nonce = "42";
  const block_window_start = "100";
  const block_window_end = "150";
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
    signal_threshold: "100",
    price_observations,
    oracle_root,
    is_long_entry: "1",
    is_short_entry: "0",
    is_exit: "0",
    is_signal_flip: "0",
    is_stop_loss: "0",
    stop_loss_price: "0",
  };
}

test("GET /health lists registered classes", async () => {
  const app = createApp();
  const res = await request(app).get("/health");
  assert.equal(res.status, 200);
  assert.equal(res.body.service, "prover");
  assert.deepEqual(res.body.classes.sort(), ["hello", "momentum_v1"]);
});

test("POST /prove rejects unknown strategyClass", async () => {
  const app = createApp();
  const res = await request(app)
    .post("/prove")
    .send({ strategyClass: "made_up_v1", witnessInputs: {} });
  assert.equal(res.status, 400);
  assert.match(res.body.error, /unknown strategyClass/);
});

test("POST /prove rejects missing fields", async () => {
  const app = createApp();
  const res = await request(app).post("/prove").send({});
  assert.equal(res.status, 400);
});

test("POST /prove momentum_v1 returns a proof that verifies off-chain", async () => {
  const app = createApp();
  const res = await request(app)
    .post("/prove")
    .send({ strategyClass: "momentum_v1", witnessInputs: buildValidMomentumInput() });

  assert.equal(res.status, 200, `expected 200, got ${res.status}: ${JSON.stringify(res.body)}`);
  const { proof, publicSignals } = res.body;
  assert.ok(proof, "proof present");
  assert.equal(publicSignals.length, 11, "11 public signals");

  // Off-chain verify against the snarkjs vkey. The on-chain MomentumV1Verifier.sol
  // is generated from this same vkey so an off-chain pass implies on-chain pass
  // (asserted in contracts/test/MomentumV1Verifier.t.sol).
  const vkey = JSON.parse(await fs.readFile(VKEY_PATH, "utf8"));
  const ok = await snarkjs.groth16.verify(vkey, publicSignals, proof);
  assert.equal(ok, true, "proof must verify against momentum_v1 vkey");
});

test("POST /prove momentum_v1 fails closed on bad witness (e.g. amount over cap)", async () => {
  const app = createApp();
  const bad = buildValidMomentumInput();
  bad.amount_in = "9999000000000000000000"; // exceeds max_position_size
  bad.trade_hash = poseidonHash([
    bad.declared_class,
    bad.asset_in,
    bad.asset_out,
    bad.amount_in,
    bad.min_amount_out,
    bad.trade_direction,
    bad.allocator_address,
    bad.nonce,
  ]);
  const res = await request(app)
    .post("/prove")
    .send({ strategyClass: "momentum_v1", witnessInputs: bad });
  assert.equal(res.status, 503);
  assert.ok(res.body.error, "error message present");
});
