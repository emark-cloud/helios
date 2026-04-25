// Helios — momentum_v1 proof generation benchmark.
//
// Runs N witness+proof generations end-to-end and reports p50/p95/p99
// latency. Phase 1 target: p95 ≤ 2_000 ms on a developer laptop.

const path = require("node:path");
const fs = require("node:fs");
const snarkjs = require("snarkjs");
const { buildPoseidon } = require("circomlibjs");

const BUILD = path.resolve(__dirname, "../build/momentum_v1");
const WASM = path.join(BUILD, "momentum_v1.wasm");
const ZKEY = path.join(BUILD, "momentum_v1.zkey");
const VKEY = path.join(BUILD, "verification_key.json");

const RUNS = parseInt(process.env.RUNS || "20", 10);

function asField(n) {
  return BigInt(n).toString();
}

async function buildInput(poseidon) {
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

  return {
    trade_hash: ph([
      declared_class,
      asset_in,
      asset_out,
      amount_in,
      min_amount_out,
      trade_direction,
      allocator_address,
      nonce,
    ]),
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
    oracle_root: chained(price_observations),
    is_long_entry: "1",
    is_short_entry: "0",
    is_exit: "0",
    is_signal_flip: "0",
    is_stop_loss: "0",
    stop_loss_price: "0",
  };
}

function pct(sortedMs, p) {
  return sortedMs[Math.min(sortedMs.length - 1, Math.floor((sortedMs.length * p) / 100))];
}

(async () => {
  for (const f of [WASM, ZKEY, VKEY]) {
    if (!fs.existsSync(f)) {
      console.error(`missing build artifact: ${f}\nrun \`make momentum_v1\` first.`);
      process.exit(1);
    }
  }
  const poseidon = await buildPoseidon();
  const input = await buildInput(poseidon);
  const vkey = JSON.parse(fs.readFileSync(VKEY));

  console.log(`benchmarking momentum_v1 proof generation (N=${RUNS})…`);
  const samples = [];
  for (let i = 0; i < RUNS; i++) {
    const t0 = process.hrtime.bigint();
    const { proof, publicSignals } = await snarkjs.groth16.fullProve(input, WASM, ZKEY);
    const ok = await snarkjs.groth16.verify(vkey, publicSignals, proof);
    if (!ok) throw new Error("proof failed verification");
    const elapsedMs = Number(process.hrtime.bigint() - t0) / 1_000_000;
    samples.push(elapsedMs);
    process.stdout.write(`.${i + 1 === RUNS ? "\n" : ""}`);
  }
  samples.sort((a, b) => a - b);
  console.log(`p50:  ${pct(samples, 50).toFixed(0)} ms`);
  console.log(`p95:  ${pct(samples, 95).toFixed(0)} ms`);
  console.log(`p99:  ${pct(samples, 99).toFixed(0)} ms`);
  console.log(`min:  ${samples[0].toFixed(0)} ms`);
  console.log(`max:  ${samples[samples.length - 1].toFixed(0)} ms`);
  // Same FileHandle-leak workaround as the test runner.
  setImmediate(() => process.exit(0));
})();
