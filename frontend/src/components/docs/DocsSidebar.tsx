/**
 * Persistent docs navigation. Grouped entries from the manifest; the
 * active entry mirrors TopNav's amber treatment (DESIGN.md — no smooth
 * easings; active state is discrete).
 */

"use client";

import Link from "next/link";
import type { Route } from "next";
import { usePathname } from "next/navigation";

import { DOCS_GROUPS, docHref } from "@/lib/docs/manifest";
import { cn } from "@/lib/cn";

export function DocsSidebar(): JSX.Element {
  const pathname = usePathname();
  return (
    <nav
      aria-label="Documentation"
      className="flex flex-col gap-6 lg:sticky lg:top-16 lg:max-h-[calc(100vh-5rem)] lg:overflow-y-auto"
    >
      <Link
        href="/docs"
        className={cn(
          "text-[12px] uppercase tracking-[0.16em] transition-none",
          pathname === "/docs"
            ? "text-amber"
            : "text-fg-muted hover:text-fg-primary",
        )}
        aria-current={pathname === "/docs" ? "page" : undefined}
      >
        Overview
      </Link>
      {DOCS_GROUPS.map((group) => (
        <div key={group.id} className="flex flex-col gap-2">
          <p className="text-[12px] uppercase tracking-[0.16em] text-fg-muted">
            {group.label}
          </p>
          <ul className="flex flex-col gap-1">
            {group.entries.map((entry) => {
              const href = docHref(entry);
              const active = pathname === href;
              return (
                <li key={href}>
                  <Link
                    href={href as Route}
                    className={cn(
                      "block border-l-2 py-1 pl-3 text-sm transition-none",
                      active
                        ? "border-amber text-amber"
                        : "border-transparent text-fg-secondary hover:text-fg-primary",
                    )}
                    aria-current={active ? "page" : undefined}
                  >
                    {entry.title}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}
