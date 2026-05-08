/**
 * Chain definitions for wagmi/viem.
 * Kite testnet is the canonical chain; Base/Arbitrum are execution
 * venues introduced in Phase 5. Each chain's RPC URL falls back to a
 * hosted public endpoint when the matching `NEXT_PUBLIC_*_RPC_URL` env
 * is unset, so a fresh `.env` still boots the dashboard.
 */
import { defineChain } from "viem";
import { arbitrumSepolia as viemArbSepolia, baseSepolia as viemBaseSepolia } from "viem/chains";

export const kiteTestnet = defineChain({
  id: 2368,
  name: "Kite Testnet",
  nativeCurrency: { name: "KITE", symbol: "KITE", decimals: 18 },
  rpcUrls: {
    default: {
      http: [process.env.NEXT_PUBLIC_KITE_RPC_URL ?? "https://rpc-testnet.gokite.ai"],
    },
  },
  blockExplorers: {
    default: { name: "Kitescan", url: "https://testnet.kitescan.ai" },
  },
  testnet: true,
});

/** Apply our env overrides on top of viem's stock chain definitions
 *  so the cross-chain watcher and any future signer workflows hit the
 *  RPC endpoint the operator configured. */
const baseRpcOverride = process.env.NEXT_PUBLIC_BASE_SEPOLIA_RPC_URL;
const arbRpcOverride = process.env.NEXT_PUBLIC_ARBITRUM_SEPOLIA_RPC_URL;

export const baseSepolia = baseRpcOverride && baseRpcOverride.length > 0
  ? defineChain({
      ...viemBaseSepolia,
      rpcUrls: { ...viemBaseSepolia.rpcUrls, default: { http: [baseRpcOverride] } },
    })
  : viemBaseSepolia;

export const arbitrumSepolia = arbRpcOverride && arbRpcOverride.length > 0
  ? defineChain({
      ...viemArbSepolia,
      rpcUrls: { ...viemArbSepolia.rpcUrls, default: { http: [arbRpcOverride] } },
    })
  : viemArbSepolia;

export const SUPPORTED_CHAINS = [kiteTestnet, baseSepolia, arbitrumSepolia] as const;
