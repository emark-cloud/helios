/**
 * Helios prover — HTTP wrapper around snarkjs.
 *
 * POST /prove
 *   body: { strategyClass, witnessInputs, publicInputs }
 *   200:  { proof, publicSignals }
 *   503:  { error } when snarkjs is unavailable or proof gen takes >30s
 *
 * Phase 0 ships the hello-circuit class to confirm the pipeline.
 * Phase 1 registers momentum_v1, mean_reversion_v1, yield_rotation_v1.
 *
 * No silent fallback path exists — if a proof can't be generated,
 * the client reverts and the strategy stays paused. This is by design
 * (Helios.md §7.6).
 */
import path from "node:path";
import url from "node:url";
import fs from "node:fs/promises";
import express from "express";
import pinoHttp from "pino-http";
import pino from "pino";
import * as snarkjs from "snarkjs";

const __dirname = path.dirname(url.fileURLToPath(import.meta.url));
const CIRCUITS_DIR = path.resolve(__dirname, "..", "..", "..", "circuits", "build");
const PROOF_TIMEOUT_MS = 30_000;

const log = pino({ level: process.env.LOG_LEVEL ?? "info" });

const app = express();
app.use(express.json({ limit: "1mb" }));
app.use(pinoHttp({ logger: log }));

// Registered circuit classes.
const CLASSES = new Set(["hello"]);

async function loadArtifacts(strategyClass) {
  const dir = path.join(CIRCUITS_DIR, strategyClass);
  const wasm = path.join(dir, `${strategyClass}.wasm`);
  const zkey = path.join(dir, `${strategyClass}.zkey`);
  await fs.access(wasm);
  await fs.access(zkey);
  return { wasm, zkey };
}

function withTimeout(promise, ms, label) {
  return Promise.race([
    promise,
    new Promise((_, reject) =>
      setTimeout(() => reject(new Error(`${label} timed out after ${ms}ms`)), ms)
    ),
  ]);
}

app.get("/health", (_req, res) => {
  res.json({ status: "ok", service: "prover", classes: [...CLASSES] });
});

app.post("/prove", async (req, res) => {
  const { strategyClass, witnessInputs } = req.body ?? {};
  if (!strategyClass || !witnessInputs) {
    return res.status(400).json({ error: "missing strategyClass or witnessInputs" });
  }
  if (!CLASSES.has(strategyClass)) {
    return res.status(400).json({ error: `unknown strategyClass: ${strategyClass}` });
  }

  try {
    const { wasm, zkey } = await loadArtifacts(strategyClass);
    const { proof, publicSignals } = await withTimeout(
      snarkjs.groth16.fullProve(witnessInputs, wasm, zkey),
      PROOF_TIMEOUT_MS,
      "proof generation"
    );
    return res.json({ proof, publicSignals });
  } catch (err) {
    log.error({ err: err.message, strategyClass }, "prove failed");
    return res.status(503).json({ error: err.message });
  }
});

const port = Number(process.env.PROVER_HTTP_PORT ?? process.env.PORT ?? 8004);
app.listen(port, () => {
  log.info({ port, classes: [...CLASSES] }, "prover up");
});
