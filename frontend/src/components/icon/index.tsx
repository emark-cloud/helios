/**
 * Icon set. DESIGN.md §14.1 says "Lucide, restyled" — strokes and
 * weights normalized to the system, no default Lucide. We ship the
 * icons we need as inline SVG with consistent stroke-width 1.5 and
 * `currentColor` so callers tone them via parent text color.
 *
 * If we grow past ~12 icons, swap to lucide-react with a single
 * <Icon> wrapper that overrides stroke-width — but until then this
 * is the lightest possible surface.
 */

import type { SVGProps } from "react";

const BASE_PROPS: SVGProps<SVGSVGElement> = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.5,
  strokeLinecap: "round",
  strokeLinejoin: "round",
  width: 16,
  height: 16,
};

type IconProps = SVGProps<SVGSVGElement> & { className?: string };

export function ShieldIcon({ filled, className, ...rest }: IconProps & { filled?: boolean }): JSX.Element {
  return (
    <svg {...BASE_PROPS} className={className} aria-hidden {...rest}>
      <path
        d="M12 3 4.5 6v6c0 4.5 3 7.5 7.5 9 4.5-1.5 7.5-4.5 7.5-9V6L12 3Z"
        fill={filled ? "currentColor" : "none"}
        stroke="currentColor"
      />
      {filled ? null : <path d="m9.5 12 1.8 1.8L14.8 10" />}
    </svg>
  );
}

export function ArrowUpIcon({ className, ...rest }: IconProps): JSX.Element {
  return (
    <svg {...BASE_PROPS} className={className} aria-hidden {...rest}>
      <path d="M12 5v14M6 11l6-6 6 6" />
    </svg>
  );
}

export function ArrowDownIcon({ className, ...rest }: IconProps): JSX.Element {
  return (
    <svg {...BASE_PROPS} className={className} aria-hidden {...rest}>
      <path d="M12 5v14M6 13l6 6 6-6" />
    </svg>
  );
}

export function SearchIcon({ className, ...rest }: IconProps): JSX.Element {
  return (
    <svg {...BASE_PROPS} className={className} aria-hidden {...rest}>
      <circle cx="11" cy="11" r="6.5" />
      <path d="m20 20-4.2-4.2" />
    </svg>
  );
}

export function CheckIcon({ className, ...rest }: IconProps): JSX.Element {
  return (
    <svg {...BASE_PROPS} className={className} aria-hidden {...rest}>
      <path d="m5 12.5 4.5 4.5L19 7" />
    </svg>
  );
}

export function CloseIcon({ className, ...rest }: IconProps): JSX.Element {
  return (
    <svg {...BASE_PROPS} className={className} aria-hidden {...rest}>
      <path d="M6 6l12 12M18 6 6 18" />
    </svg>
  );
}

export function FlowIcon({ className, ...rest }: IconProps): JSX.Element {
  return (
    <svg {...BASE_PROPS} className={className} aria-hidden {...rest}>
      <circle cx="6" cy="12" r="2" />
      <circle cx="18" cy="6" r="2" />
      <circle cx="18" cy="18" r="2" />
      <path d="M8 12h2c2 0 3-2 3-3l1-1M8 12h2c2 0 3 2 3 3l1 1" />
    </svg>
  );
}
