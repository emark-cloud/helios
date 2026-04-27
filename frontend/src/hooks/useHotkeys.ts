/**
 * Keyboard shortcut hook. DESIGN.md §5.5 — `J/K` list nav, `/` focus
 * search, `Esc` close, `G D / G S / G O` jump bindings. The keyboard is
 * the primary surface for power users.
 *
 * Bindings are passed in as a flat list so callers can scope them to a
 * page. The chord state (`G` then `D`) lives here; pages don't see it.
 */

"use client";

import { useEffect, useRef } from "react";

export type Hotkey = {
  /** Either a single key (e.g. "/") or a chord ("g d"). */
  combo: string;
  handler: () => void;
  /** Default true. Disable when a binding only makes sense in some state. */
  enabled?: boolean;
};

const CHORD_TIMEOUT_MS = 800;

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName.toLowerCase();
  return tag === "input" || tag === "textarea" || target.isContentEditable;
}

export function useHotkeys(hotkeys: Hotkey[]): void {
  const pendingPrefix = useRef<string | null>(null);
  const pendingTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    function clearChord(): void {
      pendingPrefix.current = null;
      if (pendingTimer.current) {
        clearTimeout(pendingTimer.current);
        pendingTimer.current = null;
      }
    }

    function onKeyDown(e: KeyboardEvent): void {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (isTypingTarget(e.target)) {
        // `Esc` to blur the input still works through the browser default.
        return;
      }

      const key = e.key.toLowerCase();

      // Resolve a pending chord first.
      if (pendingPrefix.current) {
        const combo = `${pendingPrefix.current} ${key}`;
        const match = hotkeys.find((h) => h.enabled !== false && h.combo === combo);
        clearChord();
        if (match) {
          e.preventDefault();
          match.handler();
          return;
        }
      }

      // Single-key binding.
      const direct = hotkeys.find((h) => h.enabled !== false && h.combo === key);
      if (direct) {
        e.preventDefault();
        direct.handler();
        return;
      }

      // Start a chord if any binding has this prefix.
      const startsChord = hotkeys.some((h) => h.enabled !== false && h.combo.startsWith(`${key} `));
      if (startsChord) {
        pendingPrefix.current = key;
        pendingTimer.current = setTimeout(clearChord, CHORD_TIMEOUT_MS);
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      clearChord();
    };
  }, [hotkeys]);
}
