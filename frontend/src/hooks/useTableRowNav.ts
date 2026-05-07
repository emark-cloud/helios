/**
 * J/K row navigation for tables. DESIGN.md §5.5.
 *
 * The hook owns a `selectedIndex` that callers expose as a CSS hook
 * (`data-row-selected="true"`) on the row element. Pressing `J` / `K`
 * (or `↓` / `↑`) advances the index, wrapping at boundaries; pressing
 * `Enter` activates the selected row. `/` is reserved for search-focus
 * by callers — tables that don't have a search box skip wiring it.
 *
 * Bindings only fire while the page-level focus is *not* inside a text
 * input — same guard `useHotkeys` uses. Callers should also accept that
 * `J` / `K` unbinds while a modal is open (caller's responsibility:
 * pass `enabled={!modalOpen}`).
 */

"use client";

import { useEffect, useRef, useState } from "react";

export type UseTableRowNavOptions = {
  /** Total selectable rows. Pass `0` to disable navigation entirely. */
  rowCount: number;
  /** Fires when the user activates the row (Enter on the highlight). */
  onActivate?: (_index: number) => void;
  /** Disable bindings (e.g. while a modal is open). */
  enabled?: boolean;
};

export type UseTableRowNavResult = {
  selectedIndex: number;
  setSelectedIndex: (_i: number) => void;
};

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName.toLowerCase();
  return tag === "input" || tag === "textarea" || target.isContentEditable;
}

export function useTableRowNav({
  rowCount,
  onActivate,
  enabled = true,
}: UseTableRowNavOptions): UseTableRowNavResult {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const onActivateRef = useRef(onActivate);
  onActivateRef.current = onActivate;

  // Snap selection back into range if rows shrink under us.
  useEffect(() => {
    if (rowCount === 0) return;
    if (selectedIndex >= rowCount) setSelectedIndex(rowCount - 1);
  }, [rowCount, selectedIndex]);

  useEffect(() => {
    if (!enabled || rowCount === 0) return;
    function onKeyDown(e: KeyboardEvent): void {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (isTypingTarget(e.target)) return;
      const k = e.key.toLowerCase();
      if (k === "j" || e.key === "ArrowDown") {
        e.preventDefault();
        setSelectedIndex((i) => Math.min(rowCount - 1, i + 1));
      } else if (k === "k" || e.key === "ArrowUp") {
        e.preventDefault();
        setSelectedIndex((i) => Math.max(0, i - 1));
      } else if (e.key === "Enter") {
        if (onActivateRef.current) {
          e.preventDefault();
          onActivateRef.current(selectedIndex);
        }
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [enabled, rowCount, selectedIndex]);

  return { selectedIndex, setSelectedIndex };
}
