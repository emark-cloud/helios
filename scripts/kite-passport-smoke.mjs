#!/usr/bin/env node
/**
 * Kite Passport smoke test — Phase 0 acceptance criterion.
 *
 * Exits 0 when a Passport-signed userOp lands on Kite testnet against a
 * Phase 1 contract (e.g. `UserVault.deposit`). Records the tx hash + SDK
 * version + gas cost to docs/kite-passport-notes.md under a `## Run log`
 * section.
 *
 * This file is a scaffolded skeleton. The concrete AA SDK calls will be
 * filled in once the team confirms the SDK version + Passport mint flow
 * against the live testnet (see docs/kite-passport-notes.md for the
 * open questions).
 */
import "dotenv/config";

const REQUIRED_ENV = ["KITE_RPC_URL", "KITE_PASSPORT_SIGNER_PK"];

function requireEnv() {
  const missing = REQUIRED_ENV.filter((k) => !process.env[k]);
  if (missing.length) {
    console.error(`Missing env vars: ${missing.join(", ")}`);
    console.error("Copy .env.example → .env and fill in the Kite testnet values.");
    process.exit(2);
  }
}

async function main() {
  requireEnv();

  console.log("→ Phase 0 Kite Passport smoke test");
  console.log("  This scaffold will be filled in once @gokite/aa-sdk is pinned.");
  console.log("  Manual validation path for now:");
  console.log("    1. `forge script contracts/script/DeployPhase1.s.sol --rpc-url $KITE_RPC_URL --broadcast --private-key $DEPLOYER_PK`");
  console.log("    2. Confirm contracts/deployments/kite-testnet.json was populated with Phase 1 addresses");
  console.log("    3. Call a public read via `cast call` using your EOA key (e.g. StrategyRegistry.referenceBrandHolder)");
  console.log("    4. Once @gokite/aa-sdk is installed, replace step 3 here with a Passport-signed userOp");
  process.exit(0);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
