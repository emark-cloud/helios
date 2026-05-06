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
// snarkjs.fullProve is single-threaded CPU work (~3-5s on a typical VPS
// CPU). A request shower without a cap would starve every later caller —
// each in-flight proof holds a thread until the underlying snarkjs
// computation returns (we cannot abort it; see `withTimeout` note).
// 4 is comfortable for a 4-vCPU VPS; tune via `PROVER_MAX_CONCURRENT`.
const DEFAULT_MAX_CONCURRENT = 4;

// Registered circuit classes. Adding a class requires (a) committed wasm/zkey
// under circuits/build/<class>/, (b) a generated <Class>Verifier.sol deployed
// via DeployPhase1.s.sol / DeployPhase2.s.sol, and (c) registration on
// TradeAttestationVerifier.
const REGISTERED_CLASSES = [
  "hello",
  "momentum_v1",
  "mean_reversion_v1",
  "yield_rotation_v1",
];

export function createApp({
  circuitsDir = DEFAULT_CIRCUITS_DIR,
  logger = pino({ level: process.env.LOG_LEVEL ?? "info" }),
  classes = REGISTERED_CLASSES,
  // HIGH #17 hardening (`docs/phase-3-review.md`):
  //
  //   * `authToken` — when set, every non-health request must carry
  //     `Authorization: Bearer <token>`. Defaults to unset so local
  //     dev and CI test runs continue to work without configuration.
  //     Production VPS deploys MUST set `PROVER_AUTH_TOKEN`.
  //   * `maxConcurrent` — semaphore on `POST /prove`. Excess requests
  //     get 429 instead of queueing forever; protects the worker pool
  //     from a runaway burst.
  authToken = process.env.PROVER_AUTH_TOKEN ?? "",
  maxConcurrent = Number(process.env.PROVER_MAX_CONCURRENT ?? DEFAULT_MAX_CONCURRENT),
} = {}) {
  const app = express();
  app.use(express.json({ limit: "1mb" }));
  app.use(pinoHttp({ logger }));

  const classSet = new Set(classes);
  let inFlight = 0;

  // Bearer-token gate. `/health` stays public so docker-compose's
  // healthcheck and external probes don't need the secret.
  function requireAuth(req, res, next) {
    if (!authToken) return next();
    const hdr = req.headers.authorization ?? "";
    const expected = `Bearer ${authToken}`;
    // Constant-time comparison to keep the auth check from leaking
    // token length via early-exit timing under repeated probing.
    if (hdr.length !== expected.length) {
      return res.status(401).json({ error: "unauthorized" });
    }
    let mismatch = 0;
    for (let i = 0; i < hdr.length; i += 1) {
      mismatch |= hdr.charCodeAt(i) ^ expected.charCodeAt(i);
    }
    if (mismatch !== 0) {
      return res.status(401).json({ error: "unauthorized" });
    }
    return next();
  }

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

  app.post("/prove", requireAuth, async (req, res) => {
    const { strategyClass, witnessInputs } = req.body ?? {};
    if (!strategyClass || !witnessInputs) {
      return res.status(400).json({ error: "missing strategyClass or witnessInputs" });
    }
    if (!classSet.has(strategyClass)) {
      return res.status(400).json({ error: `unknown strategyClass: ${strategyClass}` });
    }
    if (inFlight >= maxConcurrent) {
      // Caller should back off and retry. The 429 + `Retry-After`
      // signals "transient pressure," not a permanent reject. Strategy
      // runtimes already wrap proof submission in tenacity-style retry.
      res.set("Retry-After", "5");
      return res.status(429).json({ error: "prover busy" });
    }

    inFlight += 1;
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
    } finally {
      inFlight -= 1;
    }
  });

  return app;
}

function withTimeout(promise, ms, label) {
  // Caveat (HIGH #17 in `docs/phase-3-review.md`): `Promise.race` only
  // resolves the *outer* promise — `snarkjs.groth16.fullProve` accepts
  // no AbortSignal, so the underlying CPU computation continues until
  // it finishes naturally. The `inFlight` semaphore is what actually
  // bounds resource use; this timeout is a client-facing latency cap,
  // not a process-level kill. A worker-pool refactor that runs
  // snarkjs in a child process and `child.kill()`s on timeout is the
  // proper fix and is tracked as a Phase-4 follow-up.
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
