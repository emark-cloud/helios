/**
 * In-page table-of-contents extractor.
 *
 * We compute heading ids with `github-slugger` — the exact library
 * `rehype-slug@6` uses internally — and feed it EVERY heading (h1–h6)
 * in document order so its per-document dedupe counter advances
 * identically to the rendered DOM. The TOC then surfaces only h2/h3.
 * Result: a TOC `#id` href always resolves to the heading id
 * `rehype-slug` injected, with no rendered-HTML parsing.
 *
 * Fence-aware: `#` lines inside ``` / ~~~ code fences are not headings.
 * (ATX headings only; the repo's docs don't use setext underlines.)
 */

import GithubSlugger from "github-slugger";

export type TocItem = { readonly depth: 2 | 3; readonly text: string; readonly id: string };

const FENCE_RE = /^\s{0,3}(`{3,}|~{3,})/;
const ATX_RE = /^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/;

/** Reduce inline markdown in a heading to the plain text rehype-slug sees. */
function inlineToText(raw: string): string {
  return raw
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1") // images → alt
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1") // inline links → label
    .replace(/\[([^\]]*)\]\[[^\]]*\]/g, "$1") // reference links → label
    .replace(/`+/g, "") // code-span backticks
    .replace(/(\*\*|__|\*|_|~~)/g, "") // emphasis / strike markers
    .replace(/\s+/g, " ")
    .trim();
}

export function extractHeadings(markdown: string): TocItem[] {
  const slugger = new GithubSlugger();
  const items: TocItem[] = [];
  let fence: string | null = null;

  for (const line of markdown.split("\n")) {
    const fenceMatch = line.match(FENCE_RE);
    if (fenceMatch) {
      const marker = fenceMatch[1];
      if (marker !== undefined) {
        const ch = marker.charAt(0);
        if (fence === null) {
          fence = ch;
        } else if (ch === fence) {
          fence = null;
        }
      }
      continue;
    }
    if (fence !== null) continue;

    const m = line.match(ATX_RE);
    if (!m) continue;
    const hashes = m[1];
    const rawText = m[2];
    if (hashes === undefined || rawText === undefined) continue;

    const depth = hashes.length;
    const text = inlineToText(rawText);
    if (text.length === 0) continue;
    // Advance the slugger for every heading so dedupe matches
    // rehype-slug, but only surface h2/h3 in the TOC.
    const id = slugger.slug(text);
    if (depth === 2 || depth === 3) {
      items.push({ depth, text, id });
    }
  }

  return items;
}
