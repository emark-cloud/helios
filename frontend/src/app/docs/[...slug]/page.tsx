/**
 * /docs/[...slug] — one statically-rendered page per manifest entry.
 *
 * `force-static` + `dynamicParams = false`: every slug is enumerated by
 * `generateStaticParams`, the markdown is read at `next build` only,
 * and any unknown slug 404s. No filesystem access at request time.
 *
 * A single `<h1>` per page: file docs supply their own leading `#`;
 * Helios.md-section docs start at `##`, so we prepend a synthetic
 * `# {title}` for them. The TOC is extracted from the exact same
 * string we render, so anchor ids always match.
 */

import { notFound } from "next/navigation";

import { MarkdownRenderer } from "@/components/docs/MarkdownRenderer";
import { DocsToc } from "@/components/docs/DocsToc";
import {
  DOCS_BY_SLUG,
  DOCS_ENTRIES,
  DOCS_GROUPS,
  type DocEntry,
} from "@/lib/docs/manifest";
import { loadDocMarkdown } from "@/lib/docs/loader";
import { extractHeadings } from "@/lib/docs/toc";

export const dynamic = "force-static";
export const dynamicParams = false;

type Params = { slug: string[] };

export function generateStaticParams(): Params[] {
  return DOCS_ENTRIES.map((e) => ({ slug: [...e.slug] }));
}

function resolve(params: Params): DocEntry | undefined {
  return DOCS_BY_SLUG.get(params.slug.join("/"));
}

export function generateMetadata({ params }: { params: Params }): {
  title: string;
  description: string;
} {
  const entry = resolve(params);
  if (entry === undefined) {
    return { title: "Not found — Helios docs", description: "" };
  }
  return {
    title: `${entry.title} — Helios docs`,
    description: entry.description,
  };
}

function groupLabel(entry: DocEntry): string {
  for (const group of DOCS_GROUPS) {
    if (group.entries.some((e) => e.slug.join("/") === entry.slug.join("/"))) {
      return group.label;
    }
  }
  return "Documentation";
}

export default function DocPage({ params }: { params: Params }): JSX.Element {
  const entry = resolve(params);
  if (entry === undefined) notFound();

  let markdown = loadDocMarkdown(entry);
  if (entry.source.kind === "helios-section") {
    markdown = `# ${entry.title}\n\n${markdown}`;
  }
  const headings = extractHeadings(markdown);

  return (
    <div className="flex flex-col gap-2">
      <p className="text-[12px] uppercase tracking-[0.24em] text-fg-muted">
        {groupLabel(entry)}
      </p>
      <div className="lg:grid lg:grid-cols-[minmax(0,1fr)_180px] lg:gap-12">
        <article className="min-w-0 pb-16">
          <MarkdownRenderer source={markdown} />
        </article>
        <DocsToc headings={headings} />
      </div>
    </div>
  );
}
