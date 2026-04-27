/**
 * App shell — every authenticated/product page wraps in this. The top
 * nav is sticky; pages get generous left/right page padding so component
 * density stays calm at the page level (DESIGN.md §5.4).
 */

import type { ReactNode } from "react";

import { TopNav } from "./TopNav";

export function AppShell({ children }: { children: ReactNode }): JSX.Element {
  return (
    <div className="min-h-screen bg-surface-base text-fg-primary">
      <TopNav />
      <main className="mx-auto max-w-[1440px] px-6 py-8 lg:px-12">{children}</main>
    </div>
  );
}
