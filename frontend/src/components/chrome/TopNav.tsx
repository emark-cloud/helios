/**
 * Top nav. Three Phase 1 surfaces — Strategies, Onboard, Dashboard —
 * plus a hotkey hint and a wallet connect/account chip on the right.
 *
 * DESIGN.md §5.5: keyboard is first-class. `G D / G S / G O` jump,
 * `?` opens the hotkey panel. The hint trailing the wallet chip is
 * the discoverability surface — it's not a tutorial overlay, just a
 * line of monospace.
 */

"use client";

import Link from "next/link";
import dynamic from "next/dynamic";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";

import { useHotkeys } from "@/hooks/useHotkeys";
import { cn } from "@/lib/cn";

// Defer the wallet chip to the client — wagmi hooks throw during the
// static prerender Next.js does at build time.
const WalletChip = dynamic(
  () => import("./WalletChip").then((m) => m.WalletChip),
  {
    ssr: false,
    loading: () => (
      <span className="rounded-sm border border-surface-line px-2 py-1 font-mono text-xs text-fg-muted">
        Connect
      </span>
    ),
  },
);

const NAV_LINKS: Array<{ href: "/dashboard" | "/strategies" | "/allocators" | "/onboard"; label: string; chord: string }> = [
  { href: "/dashboard", label: "Dashboard", chord: "g d" },
  { href: "/strategies", label: "Strategies", chord: "g s" },
  { href: "/allocators", label: "Allocators", chord: "g a" },
  { href: "/onboard", label: "Onboard", chord: "g o" },
];

export function TopNav(): JSX.Element {
  const pathname = usePathname();
  const router = useRouter();
  const [hotkeysOpen, setHotkeysOpen] = useState(false);

  useHotkeys([
    { combo: "g d", handler: () => router.push("/dashboard") },
    { combo: "g s", handler: () => router.push("/strategies") },
    { combo: "g a", handler: () => router.push("/allocators") },
    { combo: "g o", handler: () => router.push("/onboard") },
    { combo: "?", handler: () => setHotkeysOpen((v) => !v) },
    { combo: "escape", handler: () => setHotkeysOpen(false), enabled: hotkeysOpen },
  ]);

  return (
    <>
      <header className="sticky top-0 z-10 border-b border-surface-line bg-surface-base/95 backdrop-blur-sm">
        <div className="flex h-12 items-center px-6">
          <Link
            href="/"
            className="font-display text-sm font-semibold tracking-[0.04em] text-fg-primary"
          >
            Helios
          </Link>
          <span className="mx-4 h-4 w-px bg-surface-line" aria-hidden />
          <nav className="flex items-center gap-1">
            {NAV_LINKS.map((link) => {
              const active = pathname === link.href || pathname?.startsWith(`${link.href}/`);
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={cn(
                    "rounded-sm px-2.5 py-1 text-xs uppercase tracking-[0.16em] transition-none",
                    active ? "text-amber" : "text-fg-secondary hover:text-fg-primary",
                  )}
                  aria-current={active ? "page" : undefined}
                >
                  {link.label}
                </Link>
              );
            })}
          </nav>
          <div className="ml-auto flex items-center gap-3 text-xs">
            <button
              type="button"
              className="font-mono text-fg-muted hover:text-fg-primary"
              onClick={() => setHotkeysOpen((v) => !v)}
              aria-haspopup="dialog"
              aria-expanded={hotkeysOpen}
              title="Show keyboard shortcuts (?)"
            >
              ?
            </button>
            <WalletChip />
          </div>
        </div>
      </header>
      {hotkeysOpen ? <HotkeyOverlay onClose={() => setHotkeysOpen(false)} /> : null}
    </>
  );
}

function HotkeyOverlay({ onClose }: { onClose: () => void }): JSX.Element {
  // DESIGN.md §13: modal overlay fade-in is one of the very few smooth
  // motions allowed (200ms). Everything else here is instant.
  return (
    <div
      className="fixed inset-0 z-overlay flex items-start justify-center bg-surface-base/70 pt-32"
      role="dialog"
      aria-modal="true"
      aria-labelledby="hotkey-title"
      onClick={onClose}
    >
      <div
        className="w-[420px] rounded-lg border border-surface-line bg-surface-panel p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-baseline justify-between">
          <h2 id="hotkey-title" className="font-display text-sm font-semibold text-fg-primary">
            Keyboard
          </h2>
          <span className="font-mono text-xs text-fg-muted">esc to close</span>
        </div>
        <dl className="mt-4 grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-xs">
          <Row chord="G D" label="Dashboard" />
          <Row chord="G S" label="Strategies" />
          <Row chord="G A" label="Allocators" />
          <Row chord="G O" label="Onboard" />
          <Row chord="/" label="Focus search" />
          <Row chord="J / K" label="Move row down / up" />
          <Row chord="?" label="Toggle this panel" />
          <Row chord="Esc" label="Close overlays" />
        </dl>
      </div>
    </div>
  );
}

function Row({ chord, label }: { chord: string; label: string }): JSX.Element {
  return (
    <>
      <dt>
        <kbd className="rounded-sm border border-surface-line bg-surface-elev px-1.5 py-0.5 font-mono text-[11px] text-fg-secondary">
          {chord}
        </kbd>
      </dt>
      <dd className="text-fg-secondary">{label}</dd>
    </>
  );
}
