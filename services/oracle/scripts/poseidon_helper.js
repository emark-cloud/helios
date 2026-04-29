#!/usr/bin/env node
// Helios — Poseidon helper.
//
// Tiny stdin-driven helper around `circomlibjs.buildPoseidon()` so the
// Python oracle can compute Poseidon hashes that are bit-exact against
// `circuits/momentum_v1.circom` and friends.
//
// Protocol:
//   stdin  — newline-delimited JSON requests:
//              {"op": "hash",  "inputs": ["1", "2"]}
//              {"op": "chain", "inputs": ["1", "2", "3", ...]}  // h0=P(x0); hi=P(h_{i-1}, xi)
//              {"op": "ping"}                                   // returns "pong"
//   stdout — newline-delimited JSON responses:
//              {"ok": true,  "out": "..."}
//              {"ok": false, "err": "..."}
//
// Persistent process: keeps `buildPoseidon()` warm so the WASM init cost
// (~50 ms) is paid once per oracle boot.

const readline = require("node:readline");
const { buildPoseidon } = require("circomlibjs");

async function main() {
  const poseidon = await buildPoseidon();
  const F = poseidon.F;

  function hash(inputs) {
    return F.toObject(poseidon(inputs.map((x) => BigInt(x)))).toString();
  }

  function chain(inputs) {
    if (inputs.length === 0) {
      throw new Error("chain requires at least one input");
    }
    let h = hash([inputs[0]]);
    for (let i = 1; i < inputs.length; i++) {
      h = hash([h, inputs[i]]);
    }
    return h;
  }

  const rl = readline.createInterface({ input: process.stdin });
  rl.on("line", (line) => {
    const trimmed = line.trim();
    if (!trimmed) return;
    let req;
    try {
      req = JSON.parse(trimmed);
    } catch (e) {
      process.stdout.write(JSON.stringify({ ok: false, err: `bad json: ${e.message}` }) + "\n");
      return;
    }
    try {
      let out;
      if (req.op === "hash") out = hash(req.inputs);
      else if (req.op === "chain") out = chain(req.inputs);
      else if (req.op === "ping") out = "pong";
      else throw new Error(`unknown op: ${req.op}`);
      process.stdout.write(JSON.stringify({ ok: true, out }) + "\n");
    } catch (e) {
      process.stdout.write(JSON.stringify({ ok: false, err: e.message }) + "\n");
    }
  });
  rl.on("close", () => process.exit(0));
  // Signal to the Python parent that the helper is ready to serve.
  process.stdout.write(JSON.stringify({ ok: true, out: "ready" }) + "\n");
}

main().catch((e) => {
  process.stderr.write(`fatal: ${e.message}\n`);
  process.exit(1);
});
