// Helios — generate a real yield_rotation_v1 Groth16 proof + public-signals
// fixture for Foundry tests. Output:
//   contracts/test/fixtures/yield_rotation_v1.json
//
// Mirrors the yield_rotation_v1 circuit test (`buildValidInput`):
//   from = AAVE_USDC at 4.20%, to = COMPOUND_USDC at 5.50%,
//   threshold 80 bps, bridging 30 bps. Differential 130 bps ≥ 110.

const path = require("node:path");
const fs = require("node:fs");
const snarkjs = require("snarkjs");
const { buildPoseidon } = require("circomlibjs");

const BUILD = path.resolve(__dirname, "../build/yield_rotation_v1");
const WASM = path.join(BUILD, "yield_rotation_v1.wasm");
const ZKEY = path.join(BUILD, "yield_rotation_v1.zkey");
const FIXTURE = path.resolve(
  __dirname,
  "../../contracts/test/fixtures/yield_rotation_v1.json",
);

const YIELD_DEPTH = 6; // 64 markets
const ALLOW_DEPTH = 4; // 16 allowlisted

function asField(n) {
  return BigInt(n).toString();
}

(async () => {
  const poseidon = await buildPoseidon();
  const F = poseidon.F;
  const ph = (xs) => F.toObject(poseidon(xs.map((x) => BigInt(x)))).toString();

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
        next.push(ph([cur[i], cur[i + 1]]));
      }
      levels.push(next);
    }
    return { root: levels[depth][0], levels };
  }

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

  const MARKETS = {
    AAVE_USDC: 1n,
    COMPOUND_USDC: 2n,
    AAVE_USDT: 3n,
    COMPOUND_USDT: 4n,
  };

  // Allowlist tree (16 slots): 4 active + Poseidon(0) padding.
  const allowLeaves = [
    ph([MARKETS.AAVE_USDC]),
    ph([MARKETS.COMPOUND_USDC]),
    ph([MARKETS.AAVE_USDT]),
    ph([MARKETS.COMPOUND_USDT]),
  ];
  const allowPad = ph([0]);
  while (allowLeaves.length < 1 << ALLOW_DEPTH) allowLeaves.push(allowPad);
  const allowTree = buildTree(allowLeaves, ALLOW_DEPTH);

  // Yield tree (64 slots): 4 real snapshots + Poseidon(0,0) padding.
  const yieldLeaves = [
    ph([MARKETS.AAVE_USDC, 420n]),
    ph([MARKETS.COMPOUND_USDC, 550n]),
    ph([MARKETS.AAVE_USDT, 380n]),
    ph([MARKETS.COMPOUND_USDT, 500n]),
  ];
  const yieldPad = ph([0, 0]);
  while (yieldLeaves.length < 1 << YIELD_DEPTH) yieldLeaves.push(yieldPad);
  const yieldTree = buildTree(yieldLeaves, YIELD_DEPTH);

  const yp_from = proveInclusion(yieldTree, 0, YIELD_DEPTH);
  const yp_to = proveInclusion(yieldTree, 1, YIELD_DEPTH);
  const ap_from = proveInclusion(allowTree, 0, ALLOW_DEPTH);
  const ap_to = proveInclusion(allowTree, 1, ALLOW_DEPTH);

  const declared_class = asField("0x9abc");
  const strategy_vault = asField("0xc0ffee0c0ffee0c0ffee0c0ffee0c0ffee0c0ffee");
  const m_from = asField(MARKETS.AAVE_USDC);
  const m_to = asField(MARKETS.COMPOUND_USDC);
  const amount_rotating = "1000000000000000000";
  const yield_oracle_root = yieldTree.root;
  const allocator_address = asField("0xa11ca7");
  const nonce = "7";
  const block_window_end = "200";
  const signal_threshold = "80";
  const bridging_cost = "30";
  const markets_allowlist_root = allowTree.root;

  const params_hash = ph([signal_threshold, bridging_cost]);

  const trade_hash = ph([
    declared_class,
    strategy_vault,
    params_hash,
    markets_allowlist_root,
    m_from,
    m_to,
    amount_rotating,
    yield_oracle_root,
    allocator_address,
    nonce,
    block_window_end,
  ]);

  const input = {
    trade_hash,
    declared_class,
    strategy_vault,
    params_hash,
    markets_allowlist_root,
    m_from,
    m_to,
    amount_rotating,
    yield_oracle_root,
    allocator_address,
    nonce,
    block_window_end,

    apy_from: "420",
    apy_to: "550",
    signal_threshold,
    bridging_cost,

    yield_path_indices_from: yp_from.path_indices,
    yield_siblings_from: yp_from.siblings,
    yield_path_indices_to: yp_to.path_indices,
    yield_siblings_to: yp_to.siblings,

    allow_path_indices_from: ap_from.path_indices,
    allow_siblings_from: ap_from.siblings,
    allow_path_indices_to: ap_to.path_indices,
    allow_siblings_to: ap_to.siblings,
  };

  console.log("generating yield_rotation_v1 proof…");
  const { proof, publicSignals } = await snarkjs.groth16.fullProve(
    input,
    WASM,
    ZKEY,
  );

  fs.mkdirSync(path.dirname(FIXTURE), { recursive: true });
  fs.writeFileSync(
    FIXTURE,
    JSON.stringify(
      {
        proof: {
          a: [proof.pi_a[0], proof.pi_a[1]],
          b: [
            [proof.pi_b[0][1], proof.pi_b[0][0]],
            [proof.pi_b[1][1], proof.pi_b[1][0]],
          ],
          c: [proof.pi_c[0], proof.pi_c[1]],
        },
        publicSignals,
      },
      null,
      2,
    ),
  );
  console.log(`wrote ${FIXTURE}`);
  console.log(`publicSignals length: ${publicSignals.length}`);
  setImmediate(() => process.exit(0));
})();
