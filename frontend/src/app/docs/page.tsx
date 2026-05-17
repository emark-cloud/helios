/**
 * /docs — documentation overview. Static; the IA is read from the
 * manifest so this stays in sync with the sidebar automatically.
 */

import Link from "next/link";
import type { Route } from "next";

import { DOCS_GROUPS, docHref } from "@/lib/docs/manifest";

export const dynamic = "force-static";

export const metadata = {
  title: "Helios — documentation",
  description:
    "Helios documentation for users and developers: concepts, operator and allocator guides, the SDKs, and the protocol reference.",
};

export default function DocsOverviewPage(): JSX.Element {
  return (
    <div className="flex flex-col gap-10">
      <header className="flex flex-col gap-3">
        <p className="text-[12px] uppercase tracking-[0.24em] text-fg-muted">
          Documentation
        </p>
        <h1 className="font-display text-3xl font-semibold leading-tight tracking-[-0.01em] text-fg-primary lg:text-4xl">
          Helios, end to end.
        </h1>
      </header>

      <div className="flex flex-col gap-8">
        {DOCS_GROUPS.map((group) => (
          <section key={group.id} aria-labelledby={`docs-grp-${group.id}`}>
            <h2
              id={`docs-grp-${group.id}`}
              className="mb-3 text-[12px] uppercase tracking-[0.16em] text-fg-muted"
            >
              {group.label}
            </h2>
            <ul className="grid grid-cols-1 gap-px overflow-hidden rounded-md border border-surface-line bg-surface-line sm:grid-cols-2">
              {group.entries.map((entry) => (
                <li key={entry.slug.join("/")} className="bg-surface-panel">
                  <Link
                    href={docHref(entry) as Route}
                    className="flex h-full flex-col gap-1.5 px-5 py-4 transition-none hover:bg-surface-elev"
                  >
                    <span className="text-sm text-fg-primary">
                      {entry.title}
                    </span>
                    <span className="text-[13px] leading-relaxed text-fg-secondary">
                      {entry.description}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
