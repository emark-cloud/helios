#!/usr/bin/env node
/**
 * verify-trade.js — Independent re-verification of a Helios attested-trade proof.
 *
 * Given a transaction hash on Kite testnet (chain id 2368), this script:
 *   1. Fetches the receipt + transaction.
 *   2. Locates the StrategyVault `TradeAttested` (or `YieldRotationAttested`)
 *      event in the receipt.
 *   3. Decodes the `executeWithProof` / `executeYieldRotationWithProof`
 *      calldata to recover the Groth16 proof bytes (a, b, c) and the
 *      `uint256[]` publicInputs the vault forwarded to TAV.
 *   4. Reads `TradeAttestationVerifier.verifierByClassMap(declaredClass)`
 *      to find the registered class verifier (an adapter exposing the
 *      `verifyProof(uint[2], uint[2][2], uint[2], uint[])` shape).
 *   5. Calls `verifier.verifyProof(a, b, c, publicInputs)` and prints
 *      a forensic summary plus PASS / FAIL.
 *
 * Why this matters: the `TradeAttested` event itself does NOT carry the
 * proof or full public-input vector — only a tradeHash + a handful of
 * scalar fields. To re-prove a judge can trust the on-chain pipeline we
 * must pull the proof from the original transaction's calldata and re-run
 * the verifier ourselves, off the same RPC. A failure here would mean an
 * event was emitted without an underlying valid Groth16 proof, which the
 * vault should make impossible (`InvalidProof()` reverts before emit).
 *
 * Usage:
 *   node scripts/verify-trade.js <tx-hash>
 *   node scripts/verify-trade.js <tx-hash> --rpc https://rpc-testnet.gokite.ai/
 *   node scripts/verify-trade.js <tx-hash> --deployments contracts/deployments/kite-testnet.json
 *
 * Exit codes:
 *   0  proof verified PASS
 *   1  proof FAIL or any decode / RPC error
 *
 * Dependencies (judges, fresh clone):
 *   npm i ethers@^6
 *
 * Smoke test:
 *   At write time (2026-05-08) no on-chain TradeAttested events exist on
 *   Kite testnet for the deployed StrategyVaults — the subgraph reports
 *   `trades: []` and a direct eth_getLogs sweep across every active and
 *   legacy vault from the subgraph startBlock 21074384 to head returns no
 *   matches. The first real attested trade will be produced when the
 *   sentinel allocator + reference operator drive a live `executeWithProof`
 *   on Kite testnet (Phase 6 demo). Once that lands:
 *     node scripts/verify-trade.js <tx-hash>
 *   should print `result: PASS`.
 */

import { ethers } from "ethers";
import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const DEFAULT_RPC = "https://rpc-testnet.gokite.ai/";
const EXPECTED_CHAIN_ID = 2368n;

const CLASS_LABELS = {
  "0x2a9aa442064b635baec37a7a259282faa5563a653a8325378d5676c6f04bc9dd": "momentum_v1",
  "0x18602f4f74172d545f5258541634e1a125c3a4e1227ee2a4cbee957d3490f1fb": "mean_reversion_v1",
  "0x2e882135c6afc3bda02a9c8a7c6a351198d97599c804a2575a3d616073a87251": "yield_rotation_v1",
};

const TAV_ABI = [
  "function verifierByClassMap(bytes32) view returns (address)",
];

const VERIFIER_ABI = [
  "function verifyProof(uint256[2] a, uint256[2][2] b, uint256[2] c, uint256[] publicInputs) view returns (bool)",
];

const STRATEGY_VAULT_ABI = [
  "event TradeAttested(address indexed strategy, address indexed allocator, bytes32 indexed tradeHash, bytes32 declaredClass, address assetIn, address assetOut, uint256 amountIn, uint256 minAmountOut, uint8 direction, uint64 blockWindowStart, uint64 blockWindowEnd)",
  "event YieldRotationAttested(address indexed strategy, address indexed allocator, bytes32 indexed tradeHash, bytes32 declaredClass, uint256 mFrom, uint256 mTo, uint256 amountRotating, bytes32 yieldOracleRoot, uint64 blockWindowStart, uint64 blockWindowEnd)",
  "function executeWithProof(bytes proof, uint256[] publicInputs, tuple(address target, uint256 value, bytes data)[] trades)",
  "function executeYieldRotationWithProof(bytes proof, uint256[] publicInputs, tuple(address target, uint256 value, bytes data)[] trades)",
];

function parseArgs(argv) {
  const args = { rpc: DEFAULT_RPC, deployments: null, txHash: null };
  const rest = argv.slice(2);
  for (let i = 0; i < rest.length; i++) {
    const a = rest[i];
    if (a === "--rpc") {
      args.rpc = rest[++i];
    } else if (a === "--deployments") {
      args.deployments = rest[++i];
    } else if (a === "--help" || a === "-h") {
      console.log("Usage: node scripts/verify-trade.js <tx-hash> [--rpc <url>] [--deployments <path>]");
      process.exit(0);
    } else if (!args.txHash && a.startsWith("0x")) {
      args.txHash = a;
    } else {
      throw new Error(`Unrecognized argument: ${a}`);
    }
  }
  if (!args.txHash) {
    throw new Error("Missing required <tx-hash> argument. Run with --help.");
  }
  if (!/^0x[0-9a-fA-F]{64}$/.test(args.txHash)) {
    throw new Error(`Bad tx hash: ${args.txHash}`);
  }
  return args;
}

function defaultDeploymentsPath() {
  const here = dirname(fileURLToPath(import.meta.url));
  return resolve(here, "..", "contracts", "deployments", "kite-testnet.json");
}

function loadDeployments(path) {
  const raw = JSON.parse(readFileSync(path, "utf8"));
  if (!raw.addresses || !raw.addresses.tradeAttestationVerifier) {
    throw new Error(`Deployments file missing addresses.tradeAttestationVerifier: ${path}`);
  }
  return raw;
}

function decodeProofBytes(proofBytes) {
  if (ethers.dataLength(proofBytes) !== 256) {
    throw new Error(`Proof must be 256 bytes (8 * uint256), got ${ethers.dataLength(proofBytes)}`);
  }
  const coder = ethers.AbiCoder.defaultAbiCoder();
  const [a, b, c] = coder.decode(["uint256[2]", "uint256[2][2]", "uint256[2]"], proofBytes);
  return { a, b, c };
}

function findAttestationLog(receipt, vaultIface) {
  const tradeTopic = vaultIface.getEvent("TradeAttested").topicHash;
  const yrTopic = vaultIface.getEvent("YieldRotationAttested").topicHash;
  for (const log of receipt.logs) {
    if (log.topics[0] === tradeTopic || log.topics[0] === yrTopic) {
      const parsed = vaultIface.parseLog({ topics: log.topics, data: log.data });
      return { log, parsed, kind: parsed.name };
    }
  }
  return null;
}

function decodeExecuteCalldata(input, vaultIface) {
  for (const fnName of ["executeWithProof", "executeYieldRotationWithProof"]) {
    const frag = vaultIface.getFunction(fnName);
    if (input.startsWith(frag.selector)) {
      const decoded = vaultIface.decodeFunctionData(frag, input);
      return { fnName, proof: decoded[0], publicInputs: decoded[1] };
    }
  }
  return null;
}

async function main() {
  const args = parseArgs(process.argv);
  const deploymentsPath = args.deployments ? resolve(args.deployments) : defaultDeploymentsPath();
  const deployments = loadDeployments(deploymentsPath);

  const provider = new ethers.JsonRpcProvider(args.rpc);
  const network = await provider.getNetwork();
  if (network.chainId !== EXPECTED_CHAIN_ID) {
    console.error(`Warning: RPC chain id is ${network.chainId}, expected ${EXPECTED_CHAIN_ID} (Kite testnet). Continuing.`);
  }

  const receipt = await provider.getTransactionReceipt(args.txHash);
  if (!receipt) throw new Error(`No receipt for tx ${args.txHash}. Tx not mined or unknown to this RPC.`);
  if (receipt.status !== 1) throw new Error(`Tx reverted (status=${receipt.status}); nothing to verify.`);

  const tx = await provider.getTransaction(args.txHash);
  if (!tx) throw new Error(`No transaction body for ${args.txHash}.`);

  const vaultIface = new ethers.Interface(STRATEGY_VAULT_ABI);

  const attestation = findAttestationLog(receipt, vaultIface);
  if (!attestation) {
    throw new Error(
      "No TradeAttested or YieldRotationAttested log in this receipt — this tx is not an attested-trade execution.",
    );
  }

  const callData = decodeExecuteCalldata(tx.data, vaultIface);
  if (!callData) {
    throw new Error(
      "Tx calldata is not executeWithProof / executeYieldRotationWithProof. The attestation event must have been emitted from a different transaction frame than this top-level call.",
    );
  }

  const { proof, publicInputs } = callData;
  const { a, b, c } = decodeProofBytes(proof);

  const declaredClass = ethers.hexlify(attestation.parsed.args.declaredClass).toLowerCase();
  const strategy = ethers.getAddress(attestation.parsed.args.strategy);
  const tradeHash = ethers.hexlify(attestation.parsed.args.tradeHash);
  const classLabel = CLASS_LABELS[declaredClass] || "unknown";

  const tav = new ethers.Contract(deployments.addresses.tradeAttestationVerifier, TAV_ABI, provider);
  const verifierAddr = await tav.verifierByClassMap(declaredClass);
  if (verifierAddr === ethers.ZeroAddress) {
    throw new Error(`No verifier registered for class ${declaredClass} on TAV ${deployments.addresses.tradeAttestationVerifier}.`);
  }

  const verifier = new ethers.Contract(verifierAddr, VERIFIER_ABI, provider);
  const piArray = publicInputs.map((x) => x);
  const ok = await verifier.verifyProof(a, b, c, piArray);

  console.log("─── Helios trade attestation re-verification ───");
  console.log(`tx:                ${args.txHash}`);
  console.log(`block:             ${receipt.blockNumber}`);
  console.log(`event:             ${attestation.kind}`);
  console.log(`strategy vault:    ${strategy}`);
  console.log(`tradeHash:         ${tradeHash}`);
  console.log(`declared class id: ${declaredClass}`);
  console.log(`class label:       ${classLabel}`);
  console.log(`class verifier:    ${verifierAddr}`);
  console.log(`TAV:               ${deployments.addresses.tradeAttestationVerifier}`);
  console.log(`pi[]  count:       ${piArray.length}`);
  console.log(`proof bytes:       256 (a[2] || b[2][2] || c[2])`);
  console.log(`result:            ${ok ? "PASS" : "FAIL"}`);

  if (!ok) process.exit(1);
}

main().catch((e) => {
  console.error(`verify-trade: ${e.message}`);
  process.exit(1);
});
