/**
 * Tiny client component for the judge page network panel: shows a
 * shortened endpoint URL with a copy-to-clipboard button. Lets us keep
 * the full URL accessible without crowding the card.
 */

"use client";

import { CopyButton } from "@/components/atoms/CopyButton";
import { cn } from "@/lib/cn";

export type CopyableEndpointProps = {
  label: string;
  url: string;
  /** Shortened display string. Defaults to host + last two path segments. */
  display?: string;
  /** Optional one-line caption rendered beneath the URL. */
  caption?: string;
  className?: string;
};

export function CopyableEndpoint({
  label,
  url,
  display,
  caption,
  className,
}: CopyableEndpointProps): JSX.Element {
  const visible = display ?? shortenUrl(url);

  return (
    <div
      className={cn(
        "flex flex-col gap-1.5 rounded-sm border border-surface-line bg-surface-panel px-3 py-2 text-[12px]",
        className,
      )}
    >
      <span className="text-fg-muted">{label}</span>
      <div className="flex items-center gap-2">
        <code className="truncate font-mono text-fg-primary" title={url}>
          {visible}
        </code>
        <CopyButton
          value={url}
          ariaLabel={`Copy ${label} URL to clipboard`}
          className="ml-auto"
        />
      </div>
      {caption ? (
        <span className="font-mono text-[12px] text-fg-muted">{caption}</span>
      ) : null}
    </div>
  );
}

function shortenUrl(url: string): string {
  try {
    const u = new URL(url);
    const segments = u.pathname.split("/").filter(Boolean);
    if (segments.length <= 2) return `${u.host}${u.pathname}`;
    const tail = segments.slice(-2).join("/");
    return `${u.host}/…/${tail}`;
  } catch {
    return url;
  }
}
