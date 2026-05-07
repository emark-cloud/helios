/**
 * /onboard — meta-strategy builder. Server-rendered chrome + a
 * client-only form chunk so wagmi hooks (`useAccount`,
 * `useSignMessage`) only run after the WagmiProvider mounts.
 */

import dynamic from "next/dynamic";

import { AppShell } from "@/components/chrome/AppShell";
import { PageHeader } from "@/components/chrome/PageHeader";

const OnboardClient = dynamic(
  () => import("@/components/onboard/OnboardClient").then((m) => m.OnboardClient),
  {
    ssr: false,
    loading: () => (
      <div className="rounded-md border border-surface-line bg-surface-panel p-12 text-center text-sm text-fg-muted">
        Loading onboarding…
      </div>
    ),
  },
);

export default function OnboardPage(): JSX.Element {
  return (
    <AppShell>
      <PageHeader
        eyebrow="Set up a meta-strategy"
        title="Meta-strategy"
        summary="Pick a template, adjust the constraints if you want to, sign once. The allocator handles the rest."
      />
      <OnboardClient />
    </AppShell>
  );
}
