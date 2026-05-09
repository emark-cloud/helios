/**
 * /judge — DESIGN.md §9.8 + TODO.md line 371.
 *
 * The page a hackathon judge lands on. Goal: a reviewer with no VPS
 * access can verify the entire system end-to-end via Kitescan +
 * Goldsky. Addresses are read from `contracts/deployments/*.json` at
 * build time so they don't drift; live tx counts pull from the
 * subgraph via `LandingStatsBand` (refresh 30s).
 *
 * Self-sufficient surfaces:
 *   - 5-step eval checklist (Helios.md §19) with deeplinks
 *   - all Kite-testnet contract addresses → Kitescan
 *   - canonical `verify-trade.js` command block
 *   - `recentTrades` from the subgraph → Kitescan deeplinks
 *
 * The "Try the demo scenario" button POSTs against Sentinel only when
 * the URL is set; otherwise it links out to the scenario script in
 * the repo with a one-line copy-runnable command. (No Sentinel
 * scenario REST endpoint exists yet — TODO.md line 396 covers
 * Sentinel chain-watching, not an HTTP scenario trigger.)
 */

import Link from "next/link";
import type { Route } from "next";

import { AppShell } from "@/components/chrome/AppShell";
import { CopyableEndpoint } from "@/components/judge/CopyableEndpoint";
import { LandingStatsBand } from "@/components/landing/LandingStatsBand";
import { JudgeRecentTrades } from "@/components/judge/JudgeRecentTrades";
import { CHAIN_ADDRESSES, CHAIN_IDS, type HeliosAddresses } from "@/lib/addresses";
import {
  explorerAddressUrl,
  explorerHomeUrl,
  explorerHost,
  formatAddress,
} from "@/lib/format";

export const metadata = {
  title: "Helios — judge eval",
  description:
    "Hackathon judge eval surface. Live tx counts, deployed addresses, verify-yourself command, 5-step eval checklist.",
};

const KITE_RPC = process.env.NEXT_PUBLIC_KITE_RPC_URL ?? "https://rpc-testnet.gokite.ai";
const GOLDSKY_DEFAULT =
  process.env.NEXT_PUBLIC_GOLDSKY_ENDPOINT ??
  "https://api.goldsky.com/api/public/project_cmodpmbv1pkd70127d9g741ek/subgraphs/helios/v0.2.0/gn";
const DEMO_VIDEO_URL = process.env.NEXT_PUBLIC_DEMO_VIDEO_URL ?? null;
const DEMO_BACKUP_VIDEO_URL = process.env.NEXT_PUBLIC_DEMO_BACKUP_VIDEO_URL ?? null;

export default function JudgePage(): JSX.Element {
  return (
    <AppShell>
      <div className="flex flex-col gap-10">
        <Header />
        <DemoBlock />
        <LandingStatsBand />
        <EvalChecklist />
        <AddressTable />
        <VerifyBlock />
        <JudgeRecentTrades />
        <ResourceLinks />
      </div>
    </AppShell>
  );
}

function Header(): JSX.Element {
  return (
    <header className="flex flex-col gap-3">
      <p className="text-[12px] uppercase tracking-[0.24em] text-fg-muted">
        Hackathon judge eval
      </p>
      <h1 className="font-display text-3xl font-semibold leading-tight tracking-[-0.01em] text-fg-primary lg:text-4xl">
        Verify Helios end-to-end.
      </h1>
      <p className="max-w-3xl text-sm leading-relaxed text-fg-secondary lg:text-base">
        Every claim on this page resolves to Kitescan or Goldsky. Live counts refresh
        every 30 seconds; addresses are read from
        <code className="ml-1 font-mono text-[12px] text-fg-primary">
          contracts/deployments/kite-testnet.json
        </code>
        at build time.
      </p>
    </header>
  );
}

function DemoBlock(): JSX.Element {
  const hasVideo = DEMO_VIDEO_URL !== null;
  return (
    <section
      aria-labelledby="judge-demo"
      className="rounded-md border border-surface-line bg-surface-panel p-6"
    >
      <div className="flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-center">
        <div className="flex flex-col gap-1">
          <h2
            id="judge-demo"
            className="text-[12px] uppercase tracking-[0.18em] text-fg-muted"
          >
            3-minute demo
          </h2>
          <p className="text-base text-fg-primary">
            Cascade → auto-defund → cross-chain reputation.
          </p>
          {hasVideo ? (
            <p className="font-mono text-[12px] text-fg-muted">
              90-second backup link to the right.
            </p>
          ) : null}
        </div>
        <div className="flex items-center gap-3">
          {hasVideo ? (
            <>
              <a
                href={DEMO_VIDEO_URL ?? "#"}
                target="_blank"
                rel="noreferrer"
                className="rounded-sm border border-amber bg-amber/10 px-4 py-2 font-mono text-xs uppercase tracking-[0.18em] text-amber transition-none hover:bg-amber/20"
              >
                Watch demo →
              </a>
              {DEMO_BACKUP_VIDEO_URL ? (
                <a
                  href={DEMO_BACKUP_VIDEO_URL}
                  target="_blank"
                  rel="noreferrer"
                  className="font-mono text-[12px] uppercase tracking-[0.18em] text-fg-secondary hover:text-fg-primary"
                >
                  90s backup
                </a>
              ) : null}
            </>
          ) : (
            <span className="rounded-sm border border-surface-line px-3 py-2 font-mono text-[12px] uppercase tracking-[0.18em] text-fg-muted">
              Recording for submission
            </span>
          )}
        </div>
      </div>
      <p className="mt-4 text-[12px] leading-relaxed text-fg-muted">
        Run the cascade locally: clone the repo, then{" "}
        <code className="font-mono text-fg-secondary">scripts/e2e-scenario.sh</code>{" "}
        against a fresh <code className="font-mono text-fg-secondary">pnpm dev</code> stack.
      </p>
    </section>
  );
}

function EvalChecklist(): JSX.Element {
  // Mirrors `Helios.md §19` so the judge has a deterministic flow.
  // Each row is a single direct link — no nested choices.
  const steps: Array<{ n: number; label: string; href: Route; description: string }> = [
    {
      n: 1,
      label: "Sign a meta-strategy",
      href: "/onboard",
      description:
        "One signature → allocator authorized to deploy capital under your constraints.",
    },
    {
      n: 2,
      label: "Watch the cascade",
      href: "/dashboard",
      description:
        "Capital lands across 3–5 strategies in 80–120ms staggered renders.",
    },
    {
      n: 3,
      label: "Inspect a strategy",
      href: "/strategies",
      description:
        "Manifest, P&L curve, recent trades, params rotation history, allocator panel.",
    },
    {
      n: 4,
      label: "Audit a proof",
      href: "/strategies",
      description:
        "Click any trade → /audit/strategy/[id] → re-run the Groth16 verifier yourself.",
    },
    {
      n: 5,
      label: "Compare allocators",
      href: "/allocators",
      description:
        "Sentinel vs Helix — fee rate, reputation, capital deployed, decisions per hour.",
    },
  ];
  return (
    <section aria-labelledby="judge-eval">
      <h2
        id="judge-eval"
        className="mb-3 text-[12px] uppercase tracking-[0.16em] text-fg-muted"
      >
        5-step eval checklist
      </h2>
      <ol className="grid grid-cols-1 gap-px overflow-hidden rounded-md border border-surface-line bg-surface-line">
        {steps.map((step) => (
          <li key={step.n} className="bg-surface-panel">
            <Link
              href={step.href}
              className="flex items-baseline gap-4 px-5 py-4 text-sm hover:bg-surface-elev"
            >
              <span className="font-mono text-[12px] uppercase tracking-[0.18em] text-fg-muted">
                {String(step.n).padStart(2, "0")}
              </span>
              <span className="flex flex-1 flex-col gap-1">
                <span className="text-fg-primary">{step.label}</span>
                <span className="text-fg-secondary">{step.description}</span>
              </span>
              <span className="font-mono text-[12px] uppercase tracking-[0.18em] text-fg-muted">
                go →
              </span>
            </Link>
          </li>
        ))}
      </ol>
    </section>
  );
}

function AddressTable(): JSX.Element {
  const kite = CHAIN_ADDRESSES["kite-testnet"];
  const kiteId = CHAIN_IDS["kite-testnet"];
  const rows = addressRows(kite);

  return (
    <section aria-labelledby="judge-addresses">
      <div className="mb-3 flex items-baseline justify-between">
        <h2
          id="judge-addresses"
          className="text-[12px] uppercase tracking-[0.16em] text-fg-muted"
        >
          Deployed addresses
        </h2>
        <span className="font-mono text-[12px] uppercase tracking-[0.16em] text-fg-muted">
          chain {kiteId} · kite testnet
        </span>
      </div>
      <div className="overflow-hidden rounded-md border border-surface-line bg-surface-panel">
        <table className="w-full text-sm">
          <thead className="border-b border-surface-line text-[12px] uppercase tracking-[0.16em] text-fg-muted">
            <tr>
              <th className="px-3 py-2.5 text-left font-normal">Contract</th>
              <th className="px-3 py-2.5 text-left font-normal">Address</th>
              <th className="px-3 py-2.5 text-right font-normal">Explorer</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const url = row.value ? explorerAddressUrl(kiteId, row.value) : null;
              return (
                <tr key={row.label} className="border-b border-surface-line last:border-b-0">
                  <td className="px-3 py-2 text-fg-primary">{row.label}</td>
                  <td className="px-3 py-2 font-mono text-[12px] text-fg-secondary">
                    {row.value ? row.value : "—"}
                  </td>
                  <td className="px-3 py-2 text-right">
                    {url ? (
                      <a
                        href={url}
                        target="_blank"
                        rel="noreferrer"
                        className="font-mono text-[12px] text-amber hover:underline"
                      >
                        {row.value ? formatAddress(row.value) : "—"} ↗
                      </a>
                    ) : (
                      <span className="font-mono text-[12px] text-fg-muted">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <ul className="mt-3 grid grid-cols-1 gap-2 text-[12px] sm:grid-cols-3">
        <li className="rounded-sm border border-surface-line bg-surface-panel px-3 py-2">
          <span className="text-fg-muted">RPC </span>
          <code className="font-mono text-fg-primary">{KITE_RPC}</code>
        </li>
        <li className="rounded-sm border border-surface-line bg-surface-panel px-3 py-2">
          <span className="text-fg-muted">Explorer </span>
          {(() => {
            const home = explorerHomeUrl(kiteId);
            const host = explorerHost(kiteId);
            return home && host ? (
              <a
                href={home}
                target="_blank"
                rel="noreferrer"
                className="font-mono text-amber hover:underline"
              >
                {host}
              </a>
            ) : (
              <span className="font-mono text-fg-muted">—</span>
            );
          })()}
        </li>
        <li>
          <CopyableEndpoint
            label="Subgraph"
            url={GOLDSKY_DEFAULT}
            caption="POST GraphQL queries here"
          />
        </li>
      </ul>
      <p className="mt-2 font-mono text-[12px] text-fg-muted">
        Cross-chain executes on Base Sepolia (84532) + Arbitrum Sepolia (421614);
        Kite testnet remains the canonical identity / reputation chain. Mainnet
        (2366) is a stretch — see <code className="text-fg-secondary">docs/deployment-strategy.md</code>.
      </p>
    </section>
  );
}

type AddressRow = { label: string; value: string | undefined };

function addressRows(addrs: HeliosAddresses): AddressRow[] {
  return [
    { label: "USDC (testnet)", value: addrs.usdc },
    { label: "Swap router", value: addrs.swapRouter },
    { label: "User vault", value: addrs.userVault },
    { label: "Allocator vault", value: addrs.allocatorVault },
    { label: "Strategy registry", value: addrs.strategyRegistry },
    { label: "Allocator registry", value: addrs.allocatorRegistry },
    { label: "Trade attestation verifier", value: addrs.tradeAttestationVerifier },
    { label: "Reputation anchor (V1)", value: addrs.reputationAnchor },
    { label: "Strategy vault — momentum (Phase-6)", value: addrs.phase6VaultMomentum },
    {
      label: "Strategy vault — mean reversion (Phase-6)",
      value: addrs.phase6VaultMeanReversion,
    },
    {
      label: "Strategy vault — yield rotation (Phase-6)",
      value: addrs.phase6VaultYieldRotation,
    },
    { label: "Mock WBTC (Phase-6 universe)", value: addrs.mWbtc },
    { label: "Mock WETH (Phase-6 universe)", value: addrs.mWeth },
    { label: "Mock SOL (Phase-6 universe)", value: addrs.mSol },
    { label: "Verifier — momentum_v1", value: addrs.momentumVerifier },
    { label: "Verifier — mean_reversion_v1", value: addrs.meanReversionVerifier },
    { label: "Verifier — yield_rotation_v1", value: addrs.yieldRotationVerifier },
  ];
}

function VerifyBlock(): JSX.Element {
  // Same command block as `/audit/strategy/[id]`'s modal so the judge
  // sees the canonical verify-yourself contract once on the judge page
  // and can copy it without leaving. Argument shape matches
  // `scripts/verify-trade.js` exactly: positional <tx-hash>, optional
  // --rpc and --deployments overrides.
  const command = `npm i ethers@^6\nnode scripts/verify-trade.js <tx-hash from /audit/strategy/[id]> \\\n  --rpc ${KITE_RPC}`;
  return (
    <section aria-labelledby="judge-verify" className="flex flex-col gap-3">
      <h2
        id="judge-verify"
        className="text-[12px] uppercase tracking-[0.16em] text-fg-muted"
      >
        Verify a trade yourself
      </h2>
      <p className="text-sm text-fg-secondary">
        Reads the on-chain Groth16 verifier directly. Returns the verifier&apos;s
        boolean output for the trade&apos;s public-input vector.
      </p>
      <pre className="overflow-x-auto rounded-md border border-surface-line bg-surface-elev px-4 py-3 font-mono text-[12px] text-fg-primary">
        {command}
      </pre>
      <p className="font-mono text-[12px] text-fg-muted">
        Source: <code className="text-fg-secondary">scripts/verify-trade.js</code>. Single
        file, single dep (<code className="text-fg-secondary">ethers@^6</code>). Exit 0 on PASS, 1 on FAIL.
      </p>
    </section>
  );
}

function ResourceLinks(): JSX.Element {
  const groups: Array<{
    label: string;
    items: Array<{ label: string; href: string; mono?: boolean }>;
  }> = [
    {
      label: "Code",
      items: [
        { label: "github.com/emark-cloud/helios", href: "https://github.com/emark-cloud/helios", mono: true },
        { label: "Subgraph", href: "https://github.com/emark-cloud/helios/tree/main/subgraph" },
        { label: "Circuits", href: "https://github.com/emark-cloud/helios/tree/main/circuits" },
        { label: "Contracts", href: "https://github.com/emark-cloud/helios/tree/main/contracts" },
      ],
    },
    {
      label: "SDKs",
      items: [
        { label: "helios-strategy-sdk (PyPI)", href: "https://pypi.org/project/helios-strategy-sdk/" },
        { label: "helios-allocator-sdk (PyPI)", href: "https://pypi.org/project/helios-allocator-sdk/" },
        { label: "helios-trader-cli (PyPI)", href: "https://pypi.org/project/helios-trader-cli/" },
        { label: "@helios/contracts-abi", href: "https://github.com/emark-cloud/helios/tree/main/packages/contracts-abi" },
      ],
    },
    {
      label: "Docs",
      items: [
        { label: "Operator guide", href: "https://github.com/emark-cloud/helios/blob/main/docs/operator-guide.md" },
        { label: "Allocator guide", href: "https://github.com/emark-cloud/helios/blob/main/docs/allocator-guide.md" },
        { label: "Reputation math", href: "https://github.com/emark-cloud/helios/blob/main/docs/reputation-math.md" },
        { label: "Threat model", href: "https://github.com/emark-cloud/helios/blob/main/docs/threat-model.md" },
      ],
    },
  ];
  return (
    <section aria-labelledby="judge-resources">
      <h2
        id="judge-resources"
        className="mb-3 text-[12px] uppercase tracking-[0.16em] text-fg-muted"
      >
        Resources
      </h2>
      <div className="grid grid-cols-1 gap-px overflow-hidden rounded-md border border-surface-line bg-surface-line lg:grid-cols-3">
        {groups.map((group) => (
          <div key={group.label} className="bg-surface-panel p-5">
            <h3 className="mb-3 text-[12px] uppercase tracking-[0.18em] text-fg-muted">
              {group.label}
            </h3>
            <ul className="flex flex-col gap-2 text-sm">
              {group.items.map((item) => (
                <li key={item.href}>
                  <a
                    href={item.href}
                    target="_blank"
                    rel="noreferrer"
                    className={
                      item.mono
                        ? "font-mono text-[12px] text-amber hover:underline"
                        : "text-fg-primary hover:text-amber"
                    }
                  >
                    {item.label} ↗
                  </a>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </section>
  );
}

