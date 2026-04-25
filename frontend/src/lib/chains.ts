/**
 * Chain definitions for wagmi/viem.
 * Kite testnet is the canonical chain; Base/Arbitrum are execution venues.
 */
import { defineChain } from "viem";
import { arbitrumSepolia, baseSepolia } from "viem/chains";

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
    default: { name: "OKLink", url: "https://www.oklink.com/kite-testnet" },
  },
  testnet: true,
});

export const SUPPORTED_CHAINS = [kiteTestnet, baseSepolia, arbitrumSepolia] as const;
