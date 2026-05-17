/**
 * In-page table of contents. Server-rendered, static anchor list — no
 * scroll-spy (DESIGN.md motion restraint; a later IntersectionObserver
 * enhancement would be purely additive). Hidden below `lg`.
 */

import type { TocItem } from "@/lib/docs/toc";
import { cn } from "@/lib/cn";

export function DocsToc({ headings }: { headings: readonly TocItem[] }): JSX.Element | null {
  if (headings.length === 0) return null;
  return (
    <nav
      aria-label="On this page"
      className="hidden lg:sticky lg:top-16 lg:block lg:self-start"
    >
      <p className="mb-3 text-[12px] uppercase tracking-[0.16em] text-fg-muted">
        On this page
      </p>
      <ul className="flex flex-col gap-1.5 border-l border-surface-line">
        {headings.map((h, i) => (
          <li key={`${h.id}-${i}`}>
            <a
              href={`#${h.id}`}
              className={cn(
                "block border-l border-transparent text-[13px] leading-snug text-fg-muted transition-none hover:text-fg-primary",
                h.depth === 3 ? "pl-6" : "pl-3",
              )}
            >
              {h.text}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
