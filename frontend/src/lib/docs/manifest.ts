/**
 * Docs site information architecture — the single source of truth for
 * which repo docs are surfaced at `/docs`, their reading order, titles,
 * and grouping.
 *
 * Content is NOT duplicated here: every entry points at a real markdown
 * file in the repo (or a section of `Helios.md`) which is read at build
 * time by `loader.ts`. To add/remove/reorder a doc, edit this file only.
 *
 * Deliberately excluded (internal/ops, not user/developer docs):
 *   wallet-inventory, demo-runbook, demo-script, helios-v1-acceptance,
 *   active-strategies, cold-start, external-contributor, backtests/*.
 * An optional "Evidence" group is provided commented-out below.
 */

export type DocSource =
  | { readonly kind: "file"; readonly repoPath: string }
  | { readonly kind: "helios-section"; readonly sections: readonly string[] };

export type DocEntry = {
  /** URL path segments after `/docs`. */
  readonly slug: readonly string[];
  readonly title: string;
  readonly description: string;
  readonly source: DocSource;
};

export type DocGroup = {
  readonly id: string;
  readonly label: string;
  readonly entries: readonly DocEntry[];
};

export const DOCS_GROUPS: readonly DocGroup[] = [
  {
    id: "concepts",
    label: "Concepts",
    entries: [
      {
        slug: ["concepts", "mission"],
        title: "Mission & narrative",
        description:
          "The one-liner, the problem, the Helios solution, and why this is the right shape.",
        source: { kind: "helios-section", sections: ["1"] },
      },
      {
        slug: ["concepts", "why-kite"],
        title: "Why Kite",
        description:
          "How Helios uses Kite's uniquely uncopiable primitives.",
        source: { kind: "helios-section", sections: ["2"] },
      },
      {
        slug: ["concepts", "glossary"],
        title: "Glossary",
        description: "Core concepts and the vocabulary used throughout Helios.",
        source: { kind: "helios-section", sections: ["3"] },
      },
      {
        slug: ["concepts", "architecture"],
        title: "System architecture",
        description:
          "High-level architecture, the seven-layer stack, and the data-flow lifecycle.",
        source: { kind: "helios-section", sections: ["4"] },
      },
      {
        slug: ["concepts", "cross-chain"],
        title: "Cross-chain architecture",
        description:
          "One identity, many execution chains: capital is chain-local (deposit per chain), Kite is the canonical identity + accounting layer, and LayerZero carries only reputation/attestations home — never principal. Why capital bridging is off, and the v2 direction.",
        source: { kind: "helios-section", sections: ["12"] },
      },
      {
        slug: ["concepts", "personas"],
        title: "Personas & journeys",
        description:
          "Capital owner, strategy operator, allocator operator, and the cross-cutting auditor.",
        source: { kind: "helios-section", sections: ["5"] },
      },
    ],
  },
  {
    id: "guides",
    label: "User Guides",
    entries: [
      {
        slug: ["guides", "operator"],
        title: "Operator guide",
        description:
          "Write a strategy class, backtest it, deploy and stake capital on Kite.",
        source: { kind: "file", repoPath: "docs/operator-guide.md" },
      },
      {
        slug: ["guides", "allocator"],
        title: "Allocator guide",
        description:
          "Write an allocator, register on-chain, and run the rank/rebalance loop.",
        source: { kind: "file", repoPath: "docs/allocator-guide.md" },
      },
      {
        slug: ["guides", "agentic-workflow"],
        title: "Agentic workflow",
        description:
          "Ship LLM-driven strategy agents on Helios — the protocol is agnostic to the signal source.",
        source: { kind: "file", repoPath: "docs/agentic-workflow.md" },
      },
    ],
  },
  {
    id: "sdk",
    label: "Developer / SDK",
    entries: [
      {
        slug: ["sdk", "strategy"],
        title: "Strategy SDK",
        description:
          "helios-strategy-sdk — implement StrategyAgent and ship a strategy.",
        source: { kind: "file", repoPath: "packages/strategy-sdk/README.md" },
      },
      {
        slug: ["sdk", "allocator"],
        title: "Allocator SDK",
        description:
          "helios-allocator-sdk — implement BaseAllocator and ship a competing allocator.",
        source: { kind: "file", repoPath: "packages/allocator-sdk/README.md" },
      },
    ],
  },
  {
    id: "reference",
    label: "Protocol Reference",
    entries: [
      {
        slug: ["reference", "reputation-math"],
        title: "Reputation math",
        description:
          "The score formula, cold-start mechanics, and anti-gaming detail.",
        source: { kind: "file", repoPath: "docs/reputation-math.md" },
      },
      {
        slug: ["reference", "circuit-specs"],
        title: "Circuit specs",
        description:
          "Public-input layout, constraint counts, and invariants for the three Groth16 circuits.",
        source: { kind: "file", repoPath: "docs/circuit-specs.md" },
      },
      {
        slug: ["reference", "threat-model"],
        title: "Threat model",
        description:
          "Trust assumptions mapped to concrete on-chain mitigations and test paths.",
        source: { kind: "file", repoPath: "docs/threat-model.md" },
      },
      {
        slug: ["reference", "cross-chain-cost-roadmap"],
        title: "Cross-chain cost roadmap",
        description:
          "LayerZero V2 fee breakdown and the cost-reduction levers for §12.1 routing.",
        source: { kind: "file", repoPath: "docs/cross-chain-cost-roadmap.md" },
      },
    ],
  },
  // Optional — uncomment to surface acceptance evidence + backtests under
  // an "Evidence" group:
  // {
  //   id: "evidence",
  //   label: "Evidence",
  //   entries: [
  //     {
  //       slug: ["evidence", "acceptance"],
  //       title: "v1 acceptance evidence",
  //       description: "End-to-end live evidence across the three chains.",
  //       source: { kind: "file", repoPath: "docs/helios-v1-acceptance.md" },
  //     },
  //     {
  //       slug: ["evidence", "backtest-momentum"],
  //       title: "Backtest — momentum_v1",
  //       description: "90-day synthetic backtest report.",
  //       source: { kind: "file", repoPath: "docs/backtests/momentum_v1_90d.md" },
  //     },
  //   ],
  // },
];

export const DOCS_ENTRIES: readonly DocEntry[] = DOCS_GROUPS.flatMap(
  (g) => g.entries,
);

const bySlug = new Map<string, DocEntry>();
for (const entry of DOCS_ENTRIES) {
  bySlug.set(entry.slug.join("/"), entry);
}

/** Lookup keyed by `slug.join("/")` — e.g. `"concepts/mission"`. */
export const DOCS_BY_SLUG: ReadonlyMap<string, DocEntry> = bySlug;

/** Absolute in-app href for a doc entry, e.g. `/docs/concepts/mission`. */
export function docHref(entry: DocEntry): string {
  return `/docs/${entry.slug.join("/")}`;
}
