// Helios — generate a real momentum_v1 Groth16 proof + public-signals fixture
// for Foundry tests. Output: contracts/test/fixtures/momentum_v1.json
//
// The Solidity test reads this JSON, ABI-encodes the (a, b, c) tuple as
// `proof`, and posts it to MomentumV1Verifier / TradeAttestationVerifier.

const path = require("node:path");
const fs = require("node:fs");
const snarkjs = require("snarkjs");
const { buildPoseidon } = require("circomlibjs");

const BUILD = path.resolve(__dirname, "../build/momentum_v1");
const WASM = path.join(BUILD, "momentum_v1.wasm");
const ZKEY = path.join(BUILD, "momentum_v1.zkey");
const FIXTURE = path.resolve(__dirname, "../../contracts/test/fixtures/momentum_v1.json");

function asField(n) {
  return BigInt(n).toString();
}

(async () => {
  const poseidon = await buildPoseidon();
  const F = poseidon.F;
  const ph = (xs) => F.toObject(poseidon(xs.map((x) => BigInt(x)))).toString();
  const chained = (obs) => {
    let h = ph([obs[0]]);
    for (let i = 1; i < obs.length; i++) h = ph([h, obs[i]]);
    return h;
  };

  const universe = Array.from({ length: 8 }, (_, i) => asField(0xaa00 + i));
  const asset_in = universe[0];
  const asset_out = universe[3];
  const amount_in = "1000000000000000000";
  const min_amount_out = "995000000000000000";
  const trade_direction = "1";
  const allocator_address = asField(0xa11ca7);
  const nonce = "42";
  const declared_class = asField("0x1234");
  const price_observations = Array.from({ length: 16 }, (_, i) => asField(1000 + i * 5));
  const oracle_root = chained(price_observations);
  const trade_hash = ph([
    declared_class,
    asset_in,
    asset_out,
    amount_in,
    min_amount_out,
    trade_direction,
    allocator_address,
    nonce,
  ]);

  const input = {
    trade_hash,
    declared_class,
    asset_in,
    asset_out,
    amount_in,
    min_amount_out,
    trade_direction,
    allocator_address,
    nonce,
    block_window_start: "100",
    block_window_end: "150",
    asset_universe: universe,
    max_position_size: "5000000000000000000",
    max_slippage_bps: "50",
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

  console.log("generating proof…");
  const { proof, publicSignals } = await snarkjs.groth16.fullProve(input, WASM, ZKEY);

  fs.mkdirSync(path.dirname(FIXTURE), { recursive: true });
  fs.writeFileSync(
    FIXTURE,
    JSON.stringify(
      {
        // The Solidity verifier expects each Fp2 element in pi_b with its
        // imaginary and real components swapped (snarkjs convention).
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
