#!/usr/bin/env node
/**
 * Generates TypeScript ABI constants + a Python stub from Foundry build output.
 *
 * Run after `forge build`. Produces:
 *   src/abis/<ContractName>.ts   — TS `as const` ABI exports
 *   src/abis/index.ts            — barrel re-export
 *   ../contracts-abi-py/src/helios_contracts_abi/abis.py  — Python constants
 */
import fs from "node:fs/promises";
import path from "node:path";
import url from "node:url";

const __dirname = path.dirname(url.fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const FOUNDRY_OUT = path.resolve(ROOT, "..", "..", "contracts", "out");
const TS_ABIS = path.join(ROOT, "src", "abis");
const PY_PACKAGE = path.resolve(ROOT, "..", "contracts-abi-py", "src", "helios_contracts_abi");

// Every contract whose ABI we publish. Phase 0 shipped interfaces only;
// later phases regenerate from their artifacts.
const CONTRACTS = [
  "IUserVault",
  "IAllocatorVault",
  "IStrategyVault",
  "IStrategyRegistry",
  "IAllocatorRegistry",
  "IReputationAnchor",
  "ITradeAttestationVerifier",
  "IHeliosOApp",
  "IOracleAnchor",
];

async function loadArtifact(name) {
  // Foundry writes to out/<File>.sol/<ContractName>.json
  // Interface files share names with their interface, so File == ContractName.
  const candidates = [
    path.join(FOUNDRY_OUT, `${name}.sol`, `${name}.json`),
  ];
  for (const p of candidates) {
    try {
      const json = JSON.parse(await fs.readFile(p, "utf8"));
      return { path: p, json };
    } catch {
      /* keep trying */
    }
  }
  throw new Error(`No Foundry artifact for ${name} (searched: ${candidates.join(", ")})`);
}

function toPyLiteral(value) {
  // Emit ABI as a Python literal (JSON-compatible).
  return JSON.stringify(value, null, 2)
    .replace(/true/g, "True")
    .replace(/false/g, "False")
    .replace(/null/g, "None");
}

async function main() {
  // Vercel / CI surfaces that bundle the frontend don't run `forge build`
  // first — the committed `src/abis/*.ts` is the canonical artifact for
  // them, so skip regeneration when Foundry hasn't produced output. The
  // local dev loop still runs `forge build` before this script and gets
  // a fresh codegen pass.
  try {
    await fs.access(FOUNDRY_OUT);
  } catch {
    console.log(`[contracts-abi] skip codegen — no Foundry out/ at ${FOUNDRY_OUT}`);
    return;
  }
  await fs.mkdir(TS_ABIS, { recursive: true });
  await fs.mkdir(PY_PACKAGE, { recursive: true });

  const tsIndex = [];
  const pyLines = [
    '"""Helios contract ABIs. Auto-generated from Foundry artifacts. Do not edit."""',
    "",
  ];

  for (const contract of CONTRACTS) {
    const { json } = await loadArtifact(contract);
    const abi = json.abi;

    // TS file
    const tsFile = path.join(TS_ABIS, `${contract}.ts`);
    const tsContent =
      `// Auto-generated. Do not edit.\n` +
      `// Source: contracts/out/${contract}.sol/${contract}.json\n\n` +
      `export const ${contract}Abi = ${JSON.stringify(abi, null, 2)} as const;\n`;
    await fs.writeFile(tsFile, tsContent);
    tsIndex.push(`export { ${contract}Abi } from "./${contract}.js";`);

    // Python entry
    pyLines.push(`${contract}_ABI = ${toPyLiteral(abi)}`);
    pyLines.push("");
  }

  await fs.writeFile(path.join(TS_ABIS, "index.ts"), tsIndex.join("\n") + "\n");

  // Re-export from src/index.ts (created once, stable).
  const rootIndex = path.join(ROOT, "src", "index.ts");
  await fs.writeFile(
    rootIndex,
    [
      `// Helios contract ABIs + addresses.`,
      `// Services, subgraph, and frontend import from here.`,
      ``,
      `export * from "./abis/index.js";`,
      `export * from "./addresses.js";`,
      ``,
    ].join("\n")
  );

  // Python file.
  await fs.writeFile(path.join(PY_PACKAGE, "abis.py"), pyLines.join("\n"));

  console.log(`✓ Generated ${CONTRACTS.length} ABI bindings (TS + Python)`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
