/**
 * Helios prover — Node.js HTTP wrapper around snarkjs.
 *
 * POST /prove
 *   body: { strategyClass, witnessInputs }
 *   200:  { proof, publicSignals }
 *   503:  { error } when snarkjs is unavailable or proof gen takes >30s
 *
 * Phase 1 ships the hello-circuit class (smoke) and momentum_v1.
 * mean_reversion_v1 + yield_rotation_v1 register in Phase 2.
 *
 * No silent fallback path exists — if a proof can't be generated,
 * the client reverts and the strategy stays paused. This is by design
 * (Helios.md §7.6).
 *
 * snarkjs version is pinned (package.json: "snarkjs": "0.7.6") because the
 * snarkjs verifier .sol scaffold and proof-encoding format are coupled —
 * bumping snarkjs requires regenerating MomentumV1Verifier.sol and
 * re-running the on-chain round-trip fixture under contracts/test/.
 */
import path from "node:path";
import url from "node:url";
import fs from "node:fs/promises";
import express from "express";
import pinoHttp from "pino-http";
import pino from "pino";
import * as snarkjs from "snarkjs";

const __dirname = path.dirname(url.fileURLToPath(import.meta.url));
const DEFAULT_CIRCUITS_DIR = path.resolve(__dirname, "..", "..", "..", "circuits", "build");
const PROOF_TIMEOUT_MS = 30_000;

// Registered circuit classes. Adding a class requires (a) committed wasm/zkey
// under circuits/build/<class>/, (b) a generated <Class>Verifier.sol deployed
// via DeployPhase1.s.sol, and (c) registration on TradeAttestationVerifier.
const REGISTERED_CLASSES = ["hello", "momentum_v1"];

export function createApp({
  circuitsDir = DEFAULT_CIRCUITS_DIR,
  logger = pino({ level: process.env.LOG_LEVEL ?? "info" }),
  classes = REGISTERED_CLASSES,
} = {}) {
  const app = express();
  app.use(express.json({ limit: "1mb" }));
  app.use(pinoHttp({ logger }));

  const classSet = new Set(classes);

  async function loadArtifacts(strategyClass) {
    const dir = path.join(circuitsDir, strategyClass);
    const wasm = path.join(dir, `${strategyClass}.wasm`);
    const zkey = path.join(dir, `${strategyClass}.zkey`);
    await fs.access(wasm);
    await fs.access(zkey);
    return { wasm, zkey };
  }

  app.get("/health", (_req, res) => {
    res.json({ status: "ok", service: "prover", classes: [...classSet] });
  });

  app.post("/prove", async (req, res) => {
    const { strategyClass, witnessInputs } = req.body ?? {};
    if (!strategyClass || !witnessInputs) {
      return res.status(400).json({ error: "missing strategyClass or witnessInputs" });
    }
    if (!classSet.has(strategyClass)) {
      return res.status(400).json({ error: `unknown strategyClass: ${strategyClass}` });
    }

    const startedAt = Date.now();
    try {
      const { wasm, zkey } = await loadArtifacts(strategyClass);
      const { proof, publicSignals } = await withTimeout(
        snarkjs.groth16.fullProve(witnessInputs, wasm, zkey),
        PROOF_TIMEOUT_MS,
        "proof generation"
      );
      logger.info(
        { strategyClass, durationMs: Date.now() - startedAt, publicSignalCount: publicSignals.length },
        "prove ok"
      );
      return res.json({ proof, publicSignals });
    } catch (err) {
      logger.error(
        { err: err.message, strategyClass, durationMs: Date.now() - startedAt },
        "prove failed"
      );
      return res.status(503).json({ error: err.message });
    }
  });

  return app;
}

function withTimeout(promise, ms, label) {
  return Promise.race([
    promise,
    new Promise((_, reject) =>
      setTimeout(() => reject(new Error(`${label} timed out after ${ms}ms`)), ms)
    ),
  ]);
}

const isMain = process.argv[1] && url.pathToFileURL(process.argv[1]).href === import.meta.url;
if (isMain) {
  const log = pino({ level: process.env.LOG_LEVEL ?? "info" });
  const app = createApp({ logger: log });
  const port = Number(process.env.PROVER_HTTP_PORT ?? process.env.PORT ?? 8004);
  app.listen(port, () => {
    log.info({ port, classes: REGISTERED_CLASSES }, "prover up");
  });
}
