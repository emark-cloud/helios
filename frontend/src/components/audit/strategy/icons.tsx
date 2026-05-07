/**
 * Local icon used by the audit strategy expansion. Matches the
 * `frontend/src/components/icon/` stroke-1.5 system.
 */

import type { SVGProps } from "react";

export function ChevronDown({ className, ...rest }: SVGProps<SVGSVGElement> & { className?: string }): JSX.Element {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      width={16}
      height={16}
      className={className}
      aria-hidden
      {...rest}
    >
      <path d="m6 9 6 6 6-6" />
    </svg>
  );
}
