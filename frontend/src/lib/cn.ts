/**
 * Tiny conditional className joiner. We don't pull `clsx` for this —
 * the repo's frontend deps are deliberately lean. Drops false / null /
 * undefined so callers can `cn("base", isActive && "active")` directly.
 */
export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}
