#!/usr/bin/env node
/**
 * Phase 0 verification: generate a Groth16 proof for the hello circuit and
 * verify it against the exported verification key. Exits non-zero on failure.
 *
 * Runs under `make test` in circuits/.
 */
const path = require("node:path");
const fs = require("node:fs/promises");
const snarkjs = require("snarkjs");

const BUILD = path.resolve(__dirname, "..", "build", "hello");

async function main() {
  const wasm = path.join(BUILD, "hello.wasm");
  const zkey = path.join(BUILD, "hello.zkey");
  const vkey = JSON.parse(
    await fs.readFile(path.join(BUILD, "verification_key.json"), "utf8")
  );

  // 6 * 7 = 42
  const input = { a: 6, b: 7, c: 42 };

  console.log("→ Generating proof for hello circuit (6 * 7 == 42)");
  const { proof, publicSignals } = await snarkjs.groth16.fullProve(input, wasm, zkey);

  console.log("→ Verifying proof off-chain");
  const ok = await snarkjs.groth16.verify(vkey, publicSignals, proof);

  if (!ok) {
    console.error("✗ Proof verification FAILED");
    process.exit(1);
  }
  console.log("✓ Proof verified. publicSignals =", publicSignals);

  // Negative test — wrong public input should fail.
  console.log("→ Negative test: verifying with tampered public signal");
  const bad = await snarkjs.groth16.verify(vkey, ["41"], proof);
  if (bad) {
    console.error("✗ Tampered proof unexpectedly verified");
    process.exit(1);
  }
  console.log("✓ Tampered proof correctly rejected");
}

main().then(
  () => process.exit(0),
  (err) => {
    console.error(err);
    process.exit(1);
  }
);
