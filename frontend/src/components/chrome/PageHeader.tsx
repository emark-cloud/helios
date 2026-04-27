/**
 * PageHeader — the "four questions in the top-left of every page"
 * header from DESIGN.md §5.7. Pages provide:
 *
 *   eyebrow   What am I looking at?
 *   title     (the surface name)
 *   summary   What's the current state? + What's changed recently?
 *   actions   What can I do?
 *
 * Structural consistency is what makes a power-user tool feel
 * learnable after twenty minutes.
 */

import type { ReactNode } from "react";

export type PageHeaderProps = {
  eyebrow: string;
  title: string;
  summary?: ReactNode;
  actions?: ReactNode;
};

export function PageHeader({ eyebrow, title, summary, actions }: PageHeaderProps): JSX.Element {
  return (
    <header className="mb-8 flex flex-col gap-4 border-b border-surface-line pb-6 lg:flex-row lg:items-end lg:justify-between">
      <div>
        <p className="text-[11px] uppercase tracking-[0.2em] text-fg-muted">{eyebrow}</p>
        <h1 className="mt-1.5 font-display text-2xl font-semibold text-fg-primary">{title}</h1>
        {summary ? <p className="mt-2 max-w-2xl text-sm text-fg-secondary">{summary}</p> : null}
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </header>
  );
}
