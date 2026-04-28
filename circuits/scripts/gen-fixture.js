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

  const max_position_size = "5000000000000000000";
  const max_slippage_bps = "50";
  const signal_threshold = "100";
  const stop_loss_price = "0";
  const params_hash = ph([max_position_size, max_slippage_bps, signal_threshold, stop_loss_price]);

  const price_observations = Array.from({ length: 16 }, (_, i) => asField(1000 + i * 5));
  const oracle_root = chained(price_observations);

  const declared_class = asField("0x1234");
  const strategy_vault = asField("0xbeef00");
  const allocator_address = asField("0xa11ca7");
  const asset_in_idx = "0";
  const asset_out_idx = "3";
  const amount_in = "1000000000000000000";
  const min_amount_out = "995000000000000000";
  const trade_direction = "1";
  const nonce = "42";
  const block_window_start = "100";
  const block_window_end = "150";

  const trade_hash = ph([
    strategy_vault,
    declared_class,
    params_hash,
    allocator_address,
    asset_in_idx,
    asset_out_idx,
    amount_in,
    min_amount_out,
    trade_direction,
    nonce,
  ]);

  const input = {
    trade_hash,
    declared_class,
    strategy_vault,
    params_hash,
    allocator_address,
    asset_in_idx,
    asset_out_idx,
    amount_in,
    min_amount_out,
    trade_direction,
    nonce,
    block_window_start,
    block_window_end,
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
