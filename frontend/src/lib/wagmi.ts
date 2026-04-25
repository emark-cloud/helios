"use client";

import { http, createConfig } from "wagmi";
import { coinbaseWallet, injected, walletConnect } from "wagmi/connectors";

import { SUPPORTED_CHAINS, kiteTestnet } from "./chains";

const projectId = process.env.NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID ?? "";

export const wagmiConfig = createConfig({
  chains: SUPPORTED_CHAINS,
  connectors: [
    injected(),
    coinbaseWallet({ appName: "Helios" }),
    ...(projectId ? [walletConnect({ projectId })] : []),
  ],
  transports: Object.fromEntries(
    SUPPORTED_CHAINS.map((c) => [c.id, http()]),
  ) as Record<number, ReturnType<typeof http>>,
  ssr: true,
});

export const DEFAULT_CHAIN = kiteTestnet;
