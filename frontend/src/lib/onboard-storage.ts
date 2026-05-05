/**
 * localStorage round-trip for the onboard `AllocatorPicker` choice.
 * Phase-3 plan WS6.B: persist the choice so re-onboarding remembers
 * (until the AA wallet's user-prefs path lands in Phase 4).
 */

import type { AllocatorChoice } from "@/lib/sentinel";

const STORAGE_KEY = "helios.onboard.allocator";

const VALID_CHOICES: ReadonlySet<AllocatorChoice> = new Set(["sentinel", "helix"]);

/// Read the persisted choice, defaulting to `"sentinel"` (the Phase-1
/// default). Returns the default during SSR (`window` undefined).
export function readAllocatorChoice(): AllocatorChoice {
  if (typeof window === "undefined") return "sentinel";
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw && (VALID_CHOICES as Set<string>).has(raw)) {
      return raw as AllocatorChoice;
    }
  } catch {
    // localStorage may be disabled (private mode, third-party cookies
    // off, etc.). Falling through to the default keeps onboarding
    // functional; the trade-off is the choice doesn't persist.
  }
  return "sentinel";
}

export function writeAllocatorChoice(choice: AllocatorChoice): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, choice);
  } catch {
    // Ignored — see `readAllocatorChoice` for the rationale.
  }
}
