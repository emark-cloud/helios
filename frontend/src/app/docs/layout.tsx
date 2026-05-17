/**
 * Docs chrome. AppShell keeps the product TopNav; inside it a two-column
 * grid pins the grouped sidebar left and gives the doc content the rest.
 * Per-page in-page TOC (the third rail) is rendered by the slug page so
 * it can pass extracted headings.
 */

import type { ReactNode } from "react";

import { AppShell } from "@/components/chrome/AppShell";
import { DocsSidebar } from "@/components/docs/DocsSidebar";

export default function DocsLayout({
  children,
}: {
  children: ReactNode;
}): JSX.Element {
  return (
    <AppShell>
      <div className="lg:grid lg:grid-cols-[200px_minmax(0,1fr)] lg:gap-12">
        <aside className="mb-8 lg:mb-0">
          <DocsSidebar />
        </aside>
        <div className="min-w-0">{children}</div>
      </div>
    </AppShell>
  );
}
