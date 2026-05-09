/**
 * Wallet connect/disconnect chip. Split from `TopNav` so we can defer
 * its render to the client — wagmi's `useAccount` / `useConnect` need
 * `WagmiProvider` in scope, and Next.js static prerender runs before
 * that provider mounts.
 */

"use client";

import { useAccount, useConnect, useDisconnect } from "wagmi";

import { usePassport } from "@/components/passport/PassportProvider";
import { formatAddress } from "@/lib/format";

export function WalletChip(): JSX.Element {
  const { address: wagmiAddress, isConnected: wagmiConnected } = useAccount();
  const passport = usePassport();
  const { connect, connectors, isPending } = useConnect();
  const { disconnect } = useDisconnect();
  const injected = connectors.find((c) => c.id === "injected") ?? connectors[0];

  // Passport AA wins so the chip always shows the address that
  // /onboard signs and /dashboard reads. Otherwise the user sees their
  // injected EOA here but the rest of the app talks to the AA.
  const address = passport.session?.aaAddress ?? wagmiAddress;
  const isConnected = Boolean(passport.session) || wagmiConnected;

  if (isConnected && address) {
    return (
      <button
        type="button"
        className="rounded-sm border border-surface-line px-2 py-1 font-mono text-xs text-fg-primary hover:border-amber/40"
        onClick={() => {
          // Passport disconnect goes through the provider's logout;
          // wagmi disconnect is a no-op when nothing is connected.
          if (passport.session) void passport.logout();
          else disconnect();
        }}
        title="Disconnect"
      >
        {formatAddress(address)}
      </button>
    );
  }

  return (
    <button
      type="button"
      className="rounded-sm border border-amber/40 px-2 py-1 font-mono text-xs text-amber hover:border-amber"
      onClick={() => injected && connect({ connector: injected })}
      disabled={isPending || !injected}
    >
      {isPending ? "Connecting…" : "Connect"}
    </button>
  );
}
