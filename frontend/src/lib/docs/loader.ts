/**
 * Build-time markdown loader for the docs site. `server-only` so it can
 * never be pulled into a client bundle.
 *
 * Repo-root reach: the Next app is rooted at `helios/frontend`, so the
 * repo root is one level up from `process.cwd()`. This mirrors the
 * already-accepted relative-depth assumption in `src/lib/addresses.ts`
 * (which imports `../../../contracts/deployments/*.json`). These reads
 * run only inside `force-static` routes, so they execute at `next build`
 * and never at request time. A missing file throws a path-naming error
 * so the build fails loudly rather than shipping a broken page.
 */

import "server-only";

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { getHeliosSections } from "./heliosSections";
import type { DocEntry } from "./manifest";

function repoRoot(): string {
  return join(process.cwd(), "..");
}

function readRepoFile(repoPath: string): string {
  const abs = join(repoRoot(), repoPath);
  try {
    return readFileSync(abs, "utf8");
  } catch (cause) {
    throw new Error(
      `Docs loader could not read "${repoPath}" (resolved to ${abs}). ` +
        `The docs manifest points at a file that does not exist — fix ` +
        `frontend/src/lib/docs/manifest.ts or restore the source file.`,
      { cause },
    );
  }
}

/** Resolve a manifest entry to its raw markdown string (build-time). */
export function loadDocMarkdown(entry: DocEntry): string {
  const { source } = entry;
  if (source.kind === "file") {
    return readRepoFile(source.repoPath);
  }
  const heliosMd = readRepoFile("Helios.md");
  return getHeliosSections(heliosMd, source.sections);
}
