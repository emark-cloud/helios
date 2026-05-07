/**
 * `/` landing — DESIGN.md §9.1.
 *
 * Calm and confident. Headline states the thesis. Live stats band
 * pulls from the subgraph (refresh on a 30s cadence). Two CTAs lead
 * into the app + the judge eval. Secondary links sit beneath in the
 * monospace key-value style used everywhere else.
 *
 * One-screen on desktop; one-tall-scroll on mobile. Amber appears
 * exactly twice — the "Enter app" CTA and the headline accent — so
 * the page sits inside the §4.3 amber budget without taking the
 * dashboard's share.
 */

import Link from "next/link";
import type { Route } from "next";

import { LandingStatsBand } from "@/components/landing/LandingStatsBand";

export const metadata = {
  title: "Helios — capital market for AI strategies",
  description:
    "A programmatic capital market for AI trading agents on Kite. One meta-strategy, autonomous allocation, ZK-attested trades, cross-chain reputation.",
};

export default function LandingPage(): JSX.Element {
  return (
    <main className="min-h-[calc(100vh-3rem)] bg-surface-base">
      <section className="mx-auto flex max-w-5xl flex-col gap-12 px-6 pb-16 pt-20 lg:gap-16 lg:px-12 lg:pt-28">
        <header className="flex flex-col gap-5">
          <p className="text-[10px] uppercase tracking-[0.24em] text-fg-muted">
            Capital market · ZK-attested · Kite
          </p>
          <h1 className="font-display text-4xl font-semibold leading-[1.05] tracking-[-0.01em] text-fg-primary lg:text-5xl">
            A capital market for AI strategies.{" "}
            <span className="text-amber">ZK-attested.</span>
          </h1>
          <p className="max-w-2xl text-base leading-relaxed text-fg-secondary lg:text-lg">
            Sign one meta-strategy. An allocator routes your capital across competing AI
            strategies. Every trade carries a Groth16 proof bound to the strategy&apos;s declared
            class. Reputation accrues from realized, attested performance and flows across
            chains via LayerZero.
          </p>
          <div className="flex flex-wrap items-center gap-3 pt-2">
            <Link
              href="/onboard"
              className="rounded-sm border border-amber bg-amber/10 px-4 py-2 font-mono text-xs uppercase tracking-[0.18em] text-amber transition-none hover:bg-amber/20"
            >
              Enter app →
            </Link>
            <Link
              href="/judge"
              className="rounded-sm border border-surface-line px-4 py-2 font-mono text-xs uppercase tracking-[0.18em] text-fg-secondary transition-none hover:border-fg-muted hover:text-fg-primary"
            >
              Read the spec
            </Link>
          </div>
        </header>

        <LandingStatsBand />

        <SecondaryLinks />
      </section>
    </main>
  );
}

function SecondaryLinks(): JSX.Element {
  // Plain key-value rows. Mirrors the dashboard's density without
  // pulling the eye — the goal is "discoverable, not loud."
  type ExternalLink = { label: string; href: string; external: true };
  type InternalLink = { label: string; href: Route; external?: false };
  const links: Array<ExternalLink | InternalLink> = [
    { label: "Source", href: "https://github.com/anthropics/helios", external: true },
    { label: "Docs", href: "https://github.com/anthropics/helios/tree/main/docs", external: true },
    { label: "Operator guide", href: "https://github.com/anthropics/helios/blob/main/docs/operator-guide.md", external: true },
    { label: "Allocator guide", href: "https://github.com/anthropics/helios/blob/main/docs/allocator-guide.md", external: true },
    { label: "Judge eval", href: "/judge" as Route },
    { label: "Strategies", href: "/strategies" as Route },
  ];
  return (
    <nav aria-label="Secondary navigation">
      <h2 className="mb-3 text-[10px] uppercase tracking-[0.16em] text-fg-muted">
        Resources
      </h2>
      <ul className="grid grid-cols-1 gap-px overflow-hidden rounded-md border border-surface-line bg-surface-line sm:grid-cols-2 lg:grid-cols-3">
        {links.map((link) => (
          <li key={link.href} className="bg-surface-panel">
            {link.external ? (
              <a
                href={link.href}
                target="_blank"
                rel="noreferrer"
                className="flex items-baseline justify-between px-4 py-3 text-sm hover:bg-surface-elev"
              >
                <span className="text-fg-primary">{link.label}</span>
                <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-fg-muted">
                  github ↗
                </span>
              </a>
            ) : (
              <Link
                href={link.href}
                className="flex items-baseline justify-between px-4 py-3 text-sm hover:bg-surface-elev"
              >
                <span className="text-fg-primary">{link.label}</span>
                <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-fg-muted">
                  →
                </span>
              </Link>
            )}
          </li>
        ))}
      </ul>
    </nav>
  );
}
