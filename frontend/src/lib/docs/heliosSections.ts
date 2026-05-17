/**
 * Helios.md section splitter. Pure over the raw spec string so it is
 * trivially unit-testable and does no file reading (the loader passes
 * the text in). A top-level section begins at a line `## <n>. <title>`
 * (exactly two hashes, a number, a dot). It runs until the next such
 * line or EOF. `## Table of contents` (no number) and `### <n>.<m>`
 * subsections do not start a new top-level section, so they stay
 * nested in their parent — which is what we want.
 *
 * Trailing `---` thematic-break separators (Helios.md places one
 * between every top-level section) and surrounding blank lines are
 * removed so a rendered concept page doesn't end on a stray rule.
 */

const SECTION_RE = /^##\s+(\d+)\.\s+/;

/** Map of section number (`"1"`, `"2"`, …) → that section's markdown. */
export function splitHeliosSections(raw: string): ReadonlyMap<string, string> {
  const lines = raw.split("\n");
  const sections = new Map<string, string[]>();
  let current: string | null = null;

  for (const line of lines) {
    const match = SECTION_RE.exec(line);
    if (match) {
      const num = match[1];
      if (num !== undefined) {
        current = num;
        sections.set(current, [line]);
        continue;
      }
    }
    if (current !== null) {
      const bucket = sections.get(current);
      if (bucket !== undefined) bucket.push(line);
    }
  }

  const out = new Map<string, string>();
  for (const [num, bucket] of sections) {
    out.set(num, trimSection(bucket));
  }
  return out;
}

function trimSection(lines: readonly string[]): string {
  const copy = [...lines];
  // Drop trailing blank lines and `---` separators.
  while (copy.length > 0) {
    const last = copy[copy.length - 1];
    if (last === undefined) break;
    const t = last.trim();
    if (t === "" || t === "---") {
      copy.pop();
      continue;
    }
    break;
  }
  return copy.join("\n").trim();
}

/**
 * Concatenate the requested Helios.md sections in the given order.
 * Throws if any requested section is absent — a renumbered spec must
 * fail the build loudly rather than ship an empty/wrong concept page.
 */
export function getHeliosSections(
  raw: string,
  numbers: readonly string[],
): string {
  const all = splitHeliosSections(raw);
  const parts: string[] = [];
  for (const num of numbers) {
    const body = all.get(num);
    if (body === undefined || body.length === 0) {
      throw new Error(
        `Helios.md section "${num}" not found. The docs manifest references ` +
          `a section that no longer exists — update frontend/src/lib/docs/manifest.ts ` +
          `or re-check Helios.md heading numbering.`,
      );
    }
    parts.push(body);
  }
  return parts.join("\n\n");
}
