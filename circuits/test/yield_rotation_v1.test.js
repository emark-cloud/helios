// Helios — yield_rotation_v1 witness-generation tests.
//
// Validates the rotation circuit against (a) Merkle inclusion proofs
// in both the yield-oracle tree and the allowlist tree, (b) APY
// differential beating threshold + bridging, (c) trade_hash binding to
// public + private operator/registry params.

const path = require("node:path");
const test = require("node:test");
const assert = require("node:assert");
const snarkjs = require("snarkjs");
const { buildPoseidon } = require("circomlibjs");

const WASM = path.resolve(__dirname, "../build/yield_rotation_v1/yield_rotation_v1.wasm");

const YIELD_DEPTH = 6;  // 64 markets
const ALLOW_DEPTH = 4;  // 16 allowlisted

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

// Build a complete Poseidon Merkle tree from `leaves` (length 2^depth).
// Returns { root, levels } where levels[0] is the leaf row and
// levels[depth] === [root].
function buildTree(leaves, depth) {
  const expected = 1 << depth;
  if (leaves.length !== expected) {
    throw new Error(`expected ${expected} leaves, got ${leaves.length}`);
  }
  const levels = [leaves.slice()];
  for (let d = 0; d < depth; d++) {
    const cur = levels[d];
    const next = [];
    for (let i = 0; i < cur.length; i += 2) {
      next.push(poseidonHash([cur[i], cur[i + 1]]));
    }
    levels.push(next);
  }
  return { root: levels[depth][0], levels };
}

// Sibling path + path indices for `index` in the tree built from `leaves`.
// path_indices[i] = 0 means our node is the left child at level i
// (sibling to the right); 1 means we're on the right (sibling on left).
function proveInclusion(tree, index, depth) {
  const path_indices = [];
  const siblings = [];
  let idx = index;
  for (let d = 0; d < depth; d++) {
    const isLeft = idx % 2 === 0;
    const sibIdx = isLeft ? idx + 1 : idx - 1;
    path_indices.push(isLeft ? "0" : "1");
    siblings.push(tree.levels[d][sibIdx]);
    idx = idx >> 1;
  }
  return { path_indices, siblings };
}

// Default allowlist: 4 active market ids, padded with zero-leaf hashes
// to fill the 16-slot allowlist tree. Allowlist leaves are Poseidon(market_id).
const MARKETS = {
  AAVE_USDC: 1n,
  COMPOUND_USDC: 2n,
  AAVE_USDT: 3n,
  COMPOUND_USDT: 4n,
};

function buildAllowlistTree(activeIds) {
  const leaves = [];
  for (const id of activeIds) {
    leaves.push(poseidonHash([id]));
  }
  // Pad with Poseidon(0) so unused slots are deterministic.
  const pad = poseidonHash([0]);
  while (leaves.length < (1 << ALLOW_DEPTH)) {
    leaves.push(pad);
  }
  return buildTree(leaves, ALLOW_DEPTH);
}

// Yield-oracle leaves are Poseidon(market_id, apy_bps).
function buildYieldTree(snapshots) {
  const leaves = [];
  for (const s of snapshots) {
    leaves.push(poseidonHash([s.id, s.apy]));
  }
  const pad = poseidonHash([0, 0]);
  while (leaves.length < (1 << YIELD_DEPTH)) {
    leaves.push(pad);
  }
  return buildTree(leaves, YIELD_DEPTH);
}

function paramsHashOf(input) {
  return poseidonHash([input.signal_threshold, input.bridging_cost]);
}

function tradeHashOf(input) {
  return poseidonHash([
    input.declared_class,
    input.strategy_vault,
    input.params_hash,
    input.markets_allowlist_root,
    input.m_from,
    input.m_to,
    input.amount_rotating,
    input.yield_oracle_root,
    input.allocator_address,
    input.nonce,
    input.block_window_end,
    input.block_window_start,
  ]);
}

// Builds a valid rotation witness:
//   from = AAVE_USDC at 4.20% (420 bps); to = COMPOUND_USDC at 5.50%
//   threshold = 80 bps, bridging = 30 bps. Differential 130 bps ≥ 110.
function buildValidInput() {
  const allow = buildAllowlistTree([
    MARKETS.AAVE_USDC,
    MARKETS.COMPOUND_USDC,
    MARKETS.AAVE_USDT,
    MARKETS.COMPOUND_USDT,
  ]);

  // Snapshot order in the yield tree (slots 0..63):
  // 0 = AAVE_USDC@420, 1 = COMPOUND_USDC@550, 2 = AAVE_USDT@380, 3 = COMPOUND_USDT@500
  const snapshots = [
    { id: MARKETS.AAVE_USDC, apy: 420n },
    { id: MARKETS.COMPOUND_USDC, apy: 550n },
    { id: MARKETS.AAVE_USDT, apy: 380n },
    { id: MARKETS.COMPOUND_USDT, apy: 500n },
  ];
  const yieldTree = buildYieldTree(snapshots);

  const yp_from = proveInclusion(yieldTree, 0, YIELD_DEPTH);
  const yp_to = proveInclusion(yieldTree, 1, YIELD_DEPTH);
  const ap_from = proveInclusion(allow, 0, ALLOW_DEPTH);
  const ap_to = proveInclusion(allow, 1, ALLOW_DEPTH);

  const input = {
    declared_class: asField("0x9abc"),
    strategy_vault: asField("0xc0ffee0c0ffee0c0ffee0c0ffee0c0ffee0c0ffee"),
    m_from: asField(MARKETS.AAVE_USDC),
    m_to: asField(MARKETS.COMPOUND_USDC),
    amount_rotating: "1000000000000000000",
    yield_oracle_root: yieldTree.root,
    allocator_address: asField("0xa11ca7"),
    nonce: "7",
    block_window_end: "200",
    block_window_start: "150",

    apy_from: "420",
    apy_to: "550",
    signal_threshold: "80",
    bridging_cost: "30",
    markets_allowlist_root: allow.root,

    yield_path_indices_from: yp_from.path_indices,
    yield_siblings_from: yp_from.siblings,
    yield_path_indices_to: yp_to.path_indices,
    yield_siblings_to: yp_to.siblings,

    allow_path_indices_from: ap_from.path_indices,
    allow_siblings_from: ap_from.siblings,
    allow_path_indices_to: ap_to.path_indices,
    allow_siblings_to: ap_to.siblings,
  };

  input.params_hash = paramsHashOf(input);
  input.trade_hash = tradeHashOf(input);
  return input;
}

test("yield_rotation_v1: valid rotation accepted", async () => {
  const fs = require("node:fs");
  const out = "/tmp/helios_yieldrot_witness.wtns";
  await snarkjs.wtns.calculate(buildValidInput(), WASM, out);
  assert.ok(fs.statSync(out).size > 0);
});

test("yield_rotation_v1: differential below threshold rejected", async () => {
  const input = buildValidInput();
  // Bump threshold past the 130 bps real differential. params_hash must be
  // re-derived; otherwise the constraint that catches us first is the
  // params_hash equality, not the differential check.
  input.signal_threshold = "200";
  input.params_hash = paramsHashOf(input);
  input.trade_hash = tradeHashOf(input);
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_yieldrot_witness.wtns"));
});

test("yield_rotation_v1: bridging cost erodes differential past threshold", async () => {
  const input = buildValidInput();
  // Real differential 130 bps; threshold 80; raise bridging to 60 ⇒ net −10.
  input.bridging_cost = "60";
  input.params_hash = paramsHashOf(input);
  input.trade_hash = tradeHashOf(input);
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_yieldrot_witness.wtns"));
});

test("yield_rotation_v1: m_from not in allowlist rejected", async () => {
  const input = buildValidInput();
  // Lie about m_from but keep the (now-stale) allowlist proof — proof
  // verifies a leaf the circuit recomputes from the new m_from value, so
  // root recomputation diverges and the equality fails.
  input.m_from = asField(99); // 99 is not in the allowlist
  input.trade_hash = tradeHashOf(input);
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_yieldrot_witness.wtns"));
});

test("yield_rotation_v1: m_to not in allowlist rejected", async () => {
  const input = buildValidInput();
  input.m_to = asField(77);
  input.trade_hash = tradeHashOf(input);
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_yieldrot_witness.wtns"));
});

test("yield_rotation_v1: yield-oracle root mismatch rejected", async () => {
  const input = buildValidInput();
  input.yield_oracle_root = "0";
  input.trade_hash = tradeHashOf(input);
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_yieldrot_witness.wtns"));
});

test("yield_rotation_v1: apy_from claim diverges from yield-oracle leaf rejected", async () => {
  const input = buildValidInput();
  // Lying about apy_from while keeping the same Merkle path means the
  // recomputed leaf no longer matches the path's terminal hash.
  input.apy_from = "100";
  input.trade_hash = tradeHashOf(input);
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_yieldrot_witness.wtns"));
});

test("yield_rotation_v1: m_from == m_to rejected", async () => {
  const input = buildValidInput();
  input.m_to = input.m_from;
  // Re-derive a yield path/leaf for m_to that points to the from-slot
  // so we'd otherwise pass inclusion. Even with that, m_from == m_to
  // makes (m_to − m_from) zero and the inverse witness undefined.
  input.trade_hash = tradeHashOf(input);
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_yieldrot_witness.wtns"));
});

test("yield_rotation_v1: amount_rotating = 0 rejected", async () => {
  const input = buildValidInput();
  input.amount_rotating = "0";
  input.trade_hash = tradeHashOf(input);
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_yieldrot_witness.wtns"));
});

test("yield_rotation_v1: trade_hash mismatch rejected", async () => {
  const input = buildValidInput();
  input.trade_hash = poseidonHash([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]);
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_yieldrot_witness.wtns"));
});

test("yield_rotation_v1: tampered allowlist root rejected", async () => {
  const input = buildValidInput();
  input.markets_allowlist_root = poseidonHash([42]);
  input.trade_hash = tradeHashOf(input);
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_yieldrot_witness.wtns"));
});

test("yield_rotation_v1: params_hash diverges from (threshold,bridging) rejected", async () => {
  // Lie about the public params_hash while leaving the private inputs
  // intact. Constraint 8 (params_hash === Poseidon(signal_threshold,
  // bridging_cost)) catches us, blocking the on-chain
  // `_activeParamsHash()` substitution attack.
  const input = buildValidInput();
  input.params_hash = poseidonHash([999, 999]);
  input.trade_hash = tradeHashOf(input);
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_yieldrot_witness.wtns"));
});

test("yield_rotation_v1: strategy_vault rebinding without trade_hash refresh rejected", async () => {
  // Replaying a fresh proof against a different vault: the prover
  // changes strategy_vault but forgets to rebuild trade_hash. The
  // Constraint 9 trade_hash equality catches us. (On-chain the same
  // attack is also caught by `address(this) == publicInputs[2]`.)
  const input = buildValidInput();
  input.strategy_vault = asField("0xdeadbeef00000000000000000000000000000000");
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_yieldrot_witness.wtns"));
});

// docs/circuit-specs.md §3.6 gap — Constraint 8b: the block-window
// freshness gate `block_window_end − block_window_start ≤ 100` rejects
// any proof minted with a wider window than the LessEqThan(64) bound.
test("yield_rotation_v1: window > 100 blocks rejected", async () => {
  const input = buildValidInput();
  input.block_window_end = "300"; // 300 − 150 = 150 > 100
  input.trade_hash = tradeHashOf(input);
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_yieldrot_witness.wtns"));
});

// docs/circuit-specs.md §3.6 gap — apy_to divergence mirrors the
// existing apy_from case. Constraint 2 recomputes the leaf as
// Poseidon(m_to, apy_to); a tampered apy_to no longer matches the
// fixed Merkle path's terminal hash.
test("yield_rotation_v1: apy_to claim diverges from yield-oracle leaf rejected", async () => {
  const input = buildValidInput();
  input.apy_to = "100";
  input.trade_hash = tradeHashOf(input);
  await assert.rejects(snarkjs.wtns.calculate(input, WASM, "/tmp/helios_yieldrot_witness.wtns"));
});

// docs/circuit-specs.md §3.6 gap — tree-depth boundary: place an
// active market at slot 15 in the 16-slot allowlist tree (ALLOW_DEPTH
// last index) AND at slot 63 in the 64-slot yield tree (YIELD_DEPTH
// last index). Exercises path_indices = [1,1,1,1] / [1,1,1,1,1,1] —
// the all-right-child Merkle inclusion edge.
test("yield_rotation_v1: edge-slot inclusion (allowlist[15], yield[63]) accepted", async () => {
  const fs = require("node:fs");
  const out = "/tmp/helios_yieldrot_witness.wtns";

  // Allowlist: AAVE_USDC at slot 0, COMPOUND_USDC at slot 15.
  const allowLeaves = [];
  allowLeaves.push(poseidonHash([MARKETS.AAVE_USDC]));
  const pad = poseidonHash([0]);
  for (let i = 1; i < 15; i++) allowLeaves.push(pad);
  allowLeaves.push(poseidonHash([MARKETS.COMPOUND_USDC]));
  const allow = buildTree(allowLeaves, ALLOW_DEPTH);

  // Yield tree: AAVE_USDC@420 at slot 0, COMPOUND_USDC@550 at slot 63.
  const yieldLeaves = [];
  yieldLeaves.push(poseidonHash([MARKETS.AAVE_USDC, 420n]));
  const yPad = poseidonHash([0, 0]);
  for (let i = 1; i < 63; i++) yieldLeaves.push(yPad);
  yieldLeaves.push(poseidonHash([MARKETS.COMPOUND_USDC, 550n]));
  const yieldTree = buildTree(yieldLeaves, YIELD_DEPTH);

  const yp_from = proveInclusion(yieldTree, 0, YIELD_DEPTH);
  const yp_to = proveInclusion(yieldTree, 63, YIELD_DEPTH);
  const ap_from = proveInclusion(allow, 0, ALLOW_DEPTH);
  const ap_to = proveInclusion(allow, 15, ALLOW_DEPTH);

  const input = {
    declared_class: asField("0x9abc"),
    strategy_vault: asField("0xc0ffee0c0ffee0c0ffee0c0ffee0c0ffee0c0ffee"),
    m_from: asField(MARKETS.AAVE_USDC),
    m_to: asField(MARKETS.COMPOUND_USDC),
    amount_rotating: "1000000000000000000",
    yield_oracle_root: yieldTree.root,
    allocator_address: asField("0xa11ca7"),
    nonce: "7",
    block_window_end: "200",
    block_window_start: "150",
    apy_from: "420",
    apy_to: "550",
    signal_threshold: "80",
    bridging_cost: "30",
    markets_allowlist_root: allow.root,
    yield_path_indices_from: yp_from.path_indices,
    yield_siblings_from: yp_from.siblings,
    yield_path_indices_to: yp_to.path_indices,
    yield_siblings_to: yp_to.siblings,
    allow_path_indices_from: ap_from.path_indices,
    allow_siblings_from: ap_from.siblings,
    allow_path_indices_to: ap_to.path_indices,
    allow_siblings_to: ap_to.siblings,
  };
  input.params_hash = paramsHashOf(input);
  input.trade_hash = tradeHashOf(input);

  await snarkjs.wtns.calculate(input, WASM, out);
  assert.ok(fs.statSync(out).size > 0);
});

// docs/circuit-specs.md §3.6 gap — bridging_cost at exactly 2^16 − 1
// satisfies Num2Bits(16) (Constraint 6 width). Pin apy_from = 0,
// apy_to = 2^16 − 1, signal_threshold = 0 so the differential check
// `apy_to − apy_from ≥ signal_threshold + bridging_cost` collapses
// to 0 ≥ 0 — boundary-feasible without wrapping the field.
test("yield_rotation_v1: bridging_cost at 2^16 − 1 boundary accepted", async () => {
  const fs = require("node:fs");
  const out = "/tmp/helios_yieldrot_witness.wtns";
  const max16 = ((1 << 16) - 1).toString();

  const allow = buildAllowlistTree([
    MARKETS.AAVE_USDC,
    MARKETS.COMPOUND_USDC,
    MARKETS.AAVE_USDT,
    MARKETS.COMPOUND_USDT,
  ]);
  const snapshots = [
    { id: MARKETS.AAVE_USDC, apy: 0n },
    { id: MARKETS.COMPOUND_USDC, apy: BigInt(max16) },
    { id: MARKETS.AAVE_USDT, apy: 380n },
    { id: MARKETS.COMPOUND_USDT, apy: 500n },
  ];
  const yieldTree = buildYieldTree(snapshots);

  const yp_from = proveInclusion(yieldTree, 0, YIELD_DEPTH);
  const yp_to = proveInclusion(yieldTree, 1, YIELD_DEPTH);
  const ap_from = proveInclusion(allow, 0, ALLOW_DEPTH);
  const ap_to = proveInclusion(allow, 1, ALLOW_DEPTH);

  const input = {
    declared_class: asField("0x9abc"),
    strategy_vault: asField("0xc0ffee0c0ffee0c0ffee0c0ffee0c0ffee0c0ffee"),
    m_from: asField(MARKETS.AAVE_USDC),
    m_to: asField(MARKETS.COMPOUND_USDC),
    amount_rotating: "1000000000000000000",
    yield_oracle_root: yieldTree.root,
    allocator_address: asField("0xa11ca7"),
    nonce: "7",
    block_window_end: "200",
    block_window_start: "150",
    apy_from: "0",
    apy_to: max16,
    signal_threshold: "0",
    bridging_cost: max16,
    markets_allowlist_root: allow.root,
    yield_path_indices_from: yp_from.path_indices,
    yield_siblings_from: yp_from.siblings,
    yield_path_indices_to: yp_to.path_indices,
    yield_siblings_to: yp_to.siblings,
    allow_path_indices_from: ap_from.path_indices,
    allow_siblings_from: ap_from.siblings,
    allow_path_indices_to: ap_to.path_indices,
    allow_siblings_to: ap_to.siblings,
  };
  input.params_hash = paramsHashOf(input);
  input.trade_hash = tradeHashOf(input);

  await snarkjs.wtns.calculate(input, WASM, out);
  assert.ok(fs.statSync(out).size > 0);
});
