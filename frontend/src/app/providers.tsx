"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import dynamic from "next/dynamic";
import { useState, type ReactNode } from "react";
import { WagmiProvider } from "wagmi";

import { wagmiConfig } from "@/lib/wagmi";

// Lazy-loaded with ssr:false because `@particle-network/auth` (pulled
// transitively by `@gokite-network/auth`) accesses `window` /
// IndexedDB at module init. Loading it on the server crashes Next
// with "ReferenceError: window is not defined".
const PassportProvider = dynamic(
  () =>
    import("@/components/passport/PassportProvider").then((m) => ({
      default: m.PassportProvider,
    })),
  { ssr: false },
);

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(() => new QueryClient());

  return (
    <WagmiProvider config={wagmiConfig}>
      <QueryClientProvider client={queryClient}>
        <PassportProvider>{children}</PassportProvider>
      </QueryClientProvider>
    </WagmiProvider>
  );
}
