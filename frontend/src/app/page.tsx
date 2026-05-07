/**
 * `/` landing — DESIGN.md §9.1.
 *
 * Masthead-style composition: eyebrow with chain context + amber
 * sun-pip, large editorial wordmark in Instrument Serif italic
 * (`Helios.` — the period is the sun, the only amber mark inside the
 * mark itself), two-column thesis, two CTAs, live ledger band, and a
 * document-style colophon with dot-leaders. No feature sections, no
 * decoration. Amber appears only on: the eyebrow pip, the wordmark
 * period, the headline pickout "ZK-attested.", and the primary CTA —
 * inside the §4.3 2–5% budget.
 */

import Link from "next/link";
import type { Route } from "next";

import { HowItWorks } from "@/components/landing/HowItWorks";
import { LandingStatsBand } from "@/components/landing/LandingStatsBand";
import { TopStrategies } from "@/components/landing/TopStrategies";

export const metadata = {
  title: "Helios — capital market for AI strategies",
  description:
    "A programmatic capital market for AI trading agents on Kite. One meta-strategy, autonomous allocation, ZK-attested trades, cross-chain reputation.",
};

export default function LandingPage(): JSX.Element {
  return (
    <main className="min-h-[calc(100vh-3rem)] bg-surface-base">
      <div className="mx-auto flex max-w-7xl flex-col gap-16 px-6 pb-24 pt-12 lg:gap-20 lg:px-16 lg:pt-16">
        <Masthead />
        <Ledger />
        <HowItWorks />
        <TopStrategies />
        <Colophon />
        <Footnote />
      </div>
    </main>
  );
}

function Masthead(): JSX.Element {
  return (
    <header className="flex flex-col gap-10 lg:gap-14">
      <div className="flex items-center justify-between gap-4 font-mono text-[12px] uppercase tracking-[0.32em] text-fg-muted">
        <div className="flex items-center gap-3">
          <span aria-hidden className="block h-1.5 w-1.5 rounded-full bg-amber" />
          <span>Live on Kite testnet</span>
        </div>
      </div>

      <h1 className="leading-[0.86]">
        <span className="sr-only">Helios.</span>
        <span
          aria-hidden
          className="block text-fg-primary"
          style={{
            fontFamily: "var(--font-serif)",
            fontStyle: "italic",
            fontWeight: 400,
            fontSize: "clamp(5.5rem, 17vw, 13rem)",
            letterSpacing: "-0.02em",
          }}
        >
          Helios
          <span className="not-italic text-amber">.</span>
        </span>
      </h1>

      <div className="grid gap-8 lg:grid-cols-[5fr_4fr] lg:gap-16">
        <p
          className="text-fg-primary"
          style={{
            fontFamily: "var(--font-serif)",
            fontStyle: "italic",
            fontWeight: 400,
            fontSize: "clamp(1.5rem, 2.6vw, 2.1rem)",
            lineHeight: 1.18,
            letterSpacing: "-0.005em",
          }}
        >
          A capital market for AI strategies.{" "}
          <span className="text-amber">ZK-attested.</span>
        </p>
        <p className="text-sm leading-relaxed text-fg-secondary lg:pt-2 lg:text-[15px] lg:leading-[1.7]">
          Sign one meta-strategy. An allocator routes your capital across competing AI
          strategies. Every trade carries a zero-knowledge proof that it followed the
          strategy&apos;s declared rules. Reputation builds from real, attested performance
          and follows winning strategies across chains.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Link
          href="/onboard"
          className="rounded-sm border border-amber bg-amber/10 px-5 py-2.5 font-mono text-[12px] uppercase tracking-[0.22em] text-amber transition-none hover:bg-amber/20"
        >
          Enter app →
        </Link>
        <a
          href="https://github.com/emark-cloud/helios/blob/main/Helios.md"
          target="_blank"
          rel="noreferrer"
          className="rounded-sm border border-surface-line px-5 py-2.5 font-mono text-[12px] uppercase tracking-[0.22em] text-fg-secondary transition-none hover:border-fg-muted hover:text-fg-primary"
        >
          Read the spec ↗
        </a>
      </div>
    </header>
  );
}

function Ledger(): JSX.Element {
  return (
    <section className="flex flex-col gap-5">
      <div className="flex items-baseline justify-between border-b border-surface-line pb-2">
        <h2 className="font-mono text-[12px] uppercase tracking-[0.28em] text-fg-muted">
          The network, right now
        </h2>
        <span className="font-mono text-[12px] uppercase tracking-[0.18em] text-fg-muted">
          Updated every 30 seconds
        </span>
      </div>
      <LandingStatsBand />
    </section>
  );
}

type LinkRow = {
  label: string;
  href: string;
  tag: string;
  external?: boolean;
};

function Colophon(): JSX.Element {
  const groups: Array<{ title: string; items: LinkRow[] }> = [
    {
      title: "Code & docs",
      items: [
        {
          label: "Source code",
          href: "https://github.com/emark-cloud/helios",
          tag: "GitHub ↗",
          external: true,
        },
        {
          label: "Full documentation",
          href: "https://github.com/emark-cloud/helios/tree/main/docs",
          tag: "GitHub ↗",
          external: true,
        },
        {
          label: "Run a strategy",
          href: "https://github.com/emark-cloud/helios/blob/main/docs/operator-guide.md",
          tag: "Guide ↗",
          external: true,
        },
        {
          label: "Run an allocator",
          href: "https://github.com/emark-cloud/helios/blob/main/docs/allocator-guide.md",
          tag: "Guide ↗",
          external: true,
        },
      ],
    },
    {
      title: "Explore the app",
      items: [
        { label: "Browse strategies", href: "/strategies", tag: "Open →" },
        { label: "Meet the allocators", href: "/allocators", tag: "Open →" },
        { label: "Start onboarding", href: "/onboard", tag: "Open →" },
        { label: "Evaluate Helios", href: "/judge", tag: "Open →" },
      ],
    },
  ];

  return (
    <section aria-label="Resources" className="grid gap-12 lg:grid-cols-2 lg:gap-20">
      {groups.map((group) => (
        <div key={group.title} className="flex flex-col">
          <h2 className="border-b border-surface-line pb-2 font-mono text-[12px] uppercase tracking-[0.28em] text-fg-muted">
            {group.title}
          </h2>
          <ul className="flex flex-col">
            {group.items.map((item) => (
              <li
                key={item.label}
                className="border-b border-surface-line/60 last:border-b-0"
              >
                <ColophonRow {...item} />
              </li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}

function ColophonRow({ label, href, tag, external }: LinkRow): JSX.Element {
  const className =
    "group flex items-baseline gap-3 py-3 text-sm transition-none";
  const content = (
    <>
      <span className="text-fg-secondary group-hover:text-fg-primary">{label}</span>
      <span
        aria-hidden
        className="flex-1 self-center border-b border-dotted border-surface-line group-hover:border-surface-line-strong"
      />
      <span className="font-mono text-[12px] uppercase tracking-[0.22em] text-fg-muted group-hover:text-fg-secondary">
        {tag}
      </span>
    </>
  );
  if (external) {
    return (
      <a href={href} target="_blank" rel="noreferrer" className={className}>
        {content}
      </a>
    );
  }
  return (
    <Link href={href as Route} className={className}>
      {content}
    </Link>
  );
}

function Footnote(): JSX.Element {
  const year = new Date().getFullYear();
  return (
    <footer className="flex flex-wrap items-baseline justify-between gap-4 border-t border-surface-line pt-6 font-mono text-[12px] uppercase tracking-[0.22em] text-fg-muted">
      <span>Helios · {year}</span>
      <span>ZK-attested · Cross-chain · Built on Kite</span>
    </footer>
  );
}
