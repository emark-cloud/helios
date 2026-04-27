/**
 * Numeric — every balance, P&L, NAV, fee, percentage, timestamp renders
 * through this. DESIGN.md §4.4 #2 makes numerics first-class, and §5.3
 * pins them to the mono face with tabular figures so columns align.
 *
 * The atom never decides color from the value — callers pass `tone` for
 * positive/negative. That's how DESIGN.md §5.2 keeps green/red as data
 * signal only and not a stylistic flourish.
 */

import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export type NumericTone = "default" | "positive" | "negative" | "muted" | "amber";

export type NumericProps = {
  children: ReactNode;
  tone?: NumericTone;
  /** Right-align inside a fixed-width column (table cells). */
  align?: "left" | "right";
  className?: string;
  title?: string;
};

const TONE_CLASS: Record<NumericTone, string> = {
  default: "text-fg-primary",
  positive: "text-signal-positive",
  negative: "text-signal-negative",
  muted: "text-fg-muted",
  amber: "text-amber",
};

export function Numeric({
  children,
  tone = "default",
  align = "left",
  className,
  title,
}: NumericProps): JSX.Element {
  return (
    <span
      className={cn("num", TONE_CLASS[tone], align === "right" && "tabular-nums text-right", className)}
      data-numeric="true"
      title={title}
    >
      {children}
    </span>
  );
}

/** Pick a tone from a numeric direction. Returns "muted" for zero. */
export function toneFor(value: number): NumericTone {
  if (!Number.isFinite(value) || value === 0) return "muted";
  return value > 0 ? "positive" : "negative";
}
