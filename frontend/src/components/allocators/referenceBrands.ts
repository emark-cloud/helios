/**
 * Static metadata for the two Helios reference brands. The on-chain
 * `Allocator` entity carries every dynamic field we need (fee, stake,
 * reputation, users) but doesn't yet hold a ranking-function summary
 * or a `homepage_url`. Per the WS6.A plan the homepage opt-in for
 * third-party allocators is a Phase-5 follow-up; until then only
 * Sentinel and Helix have first-class code links.
 *
 * Look-up is by the lower-cased on-chain name (the registry stores
 * both the production name "Helios Sentinel" and the shadow name
 * "Helios Sentinel-shadow"; we accept either).
 */

export type ReferenceBrand = {
  /** Display name with proper casing. */
  displayName: string;
  /** One-sentence ranking-function summary. */
  rankingSummary: string;
  /** GitHub permalink to the allocator implementation. */
  codeUrl: string;
};

const SENTINEL: ReferenceBrand = {
  displayName: "Helios Sentinel",
  rankingSummary:
    "Reputation × capacity × class-fit × binary fee-fit. Equal-weight allocation across the top-K eligible strategies.",
  codeUrl: "https://github.com/emark-cloud/helios/tree/main/services/sentinel",
};

const HELIX: ReferenceBrand = {
  displayName: "Helios Helix",
  rankingSummary:
    "Reputation × capacity × class-fit × continuous fee-factor (NORMAL regime). Score-weighted allocation that pulls capital toward cheaper strategies.",
  codeUrl: "https://github.com/emark-cloud/helios/tree/main/services/helix",
};

/// Maps lower-cased on-chain names (production + shadow) to the
/// reference-brand metadata. Add new brands here as they ship.
const BRANDS: Record<string, ReferenceBrand> = {
  "helios sentinel": SENTINEL,
  "helios sentinel-shadow": SENTINEL,
  "helios helix": HELIX,
  "helios helix-shadow": HELIX,
};

export function referenceBrandFor(name: string): ReferenceBrand | null {
  return BRANDS[name.toLowerCase()] ?? null;
}

/// Stable display order for the directory grid: Sentinel first, then
/// Helix, then everyone else by reputation (the GraphQL query already
/// sorts by reputation desc, so we only need to lift the two pinned
/// brands to the front).
const PIN_ORDER: string[] = ["helios sentinel", "helios helix"];

export function pinReferenceBrandsFirst<T extends { name: string }>(rows: T[]): T[] {
  const pinned: T[] = [];
  const rest: T[] = [];
  for (const row of rows) {
    const key = row.name.toLowerCase().replace(/-shadow$/, "");
    const idx = PIN_ORDER.indexOf(key);
    if (idx >= 0) pinned[idx] = row;
    else rest.push(row);
  }
  return [...pinned.filter(Boolean), ...rest];
}
