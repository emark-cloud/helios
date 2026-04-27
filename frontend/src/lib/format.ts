/**
 * Numeric + temporal formatters. The whole product reads through these so
 * tabular alignment, sign conventions, and rounding stay consistent.
 *
 * DESIGN.md §4.4 / §5.3 — numerics are first-class. Mono face + tabular
 * figures live on the `<Numeric>` atom; this module only produces strings.
 */

const USD_FMT = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 2,
});

const USD_NO_CENTS = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

const PCT_FMT = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function formatUsd(usd: number, opts?: { compact?: boolean; cents?: boolean }): string {
  if (!Number.isFinite(usd)) return "—";
  if (opts?.compact && Math.abs(usd) >= 1_000) {
    const k = usd / 1_000;
    if (Math.abs(k) >= 1_000) {
      return `$${(k / 1_000).toFixed(1)}M`;
    }
    return `$${k.toFixed(1)}k`;
  }
  return opts?.cents === false ? USD_NO_CENTS.format(usd) : USD_FMT.format(usd);
}

/** Sentinel + chain numerics arrive as integer USD (no decimals). */
export function formatUsdInt(usdInt: bigint | number, opts?: { compact?: boolean }): string {
  const n = typeof usdInt === "bigint" ? Number(usdInt) : usdInt;
  return formatUsd(n, { ...opts, cents: false });
}

export function formatBpsAsPct(bps: number, opts?: { signed?: boolean }): string {
  if (!Number.isFinite(bps)) return "—";
  const pct = bps / 100;
  const body = `${PCT_FMT.format(Math.abs(pct))}%`;
  if (!opts?.signed) return pct < 0 ? `−${body}` : body;
  if (pct > 0) return `+${body}`;
  if (pct < 0) return `−${body}`;
  return body;
}

export function formatPct(value: number, opts?: { signed?: boolean }): string {
  if (!Number.isFinite(value)) return "—";
  const body = `${PCT_FMT.format(Math.abs(value))}%`;
  if (!opts?.signed) return value < 0 ? `−${body}` : body;
  if (value > 0) return `+${body}`;
  if (value < 0) return `−${body}`;
  return body;
}

export function formatAddress(addr: string): string {
  if (!addr || addr.length < 10) return addr ?? "—";
  return `${addr.slice(0, 6)}…${addr.slice(-4)}`;
}

/** Relative time with terse units. "12s ago", "5m ago", "3h ago", "2d ago". */
export function formatRelative(tsSec: number, nowSec: number = Math.floor(Date.now() / 1000)): string {
  const dt = nowSec - tsSec;
  if (!Number.isFinite(dt) || dt < 0) return "—";
  if (dt < 60) return `${dt}s ago`;
  if (dt < 3_600) return `${Math.floor(dt / 60)}m ago`;
  if (dt < 86_400) return `${Math.floor(dt / 3_600)}h ago`;
  return `${Math.floor(dt / 86_400)}d ago`;
}

export function formatTimestamp(tsSec: number): string {
  if (!Number.isFinite(tsSec)) return "—";
  const d = new Date(tsSec * 1_000);
  return d.toLocaleString("en-US", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

const CLASS_LABELS: Record<string, string> = {
  momentum_v1: "Momentum",
  mean_reversion_v1: "Mean reversion",
  yield_rotation_v1: "Yield rotation",
};

export function formatStrategyClass(cls: string): string {
  return CLASS_LABELS[cls] ?? cls;
}

export function chainName(chainId: number): "Kite" | "Base" | "Arbitrum" | "Anvil" | "Unknown" {
  if (chainId === 2368) return "Kite";
  if (chainId === 84_532) return "Base";
  if (chainId === 421_614) return "Arbitrum";
  if (chainId === 31_337) return "Anvil";
  return "Unknown";
}

const EXPLORERS: Record<number, string> = {
  2368: "https://www.oklink.com/kite-testnet",
  84_532: "https://sepolia.basescan.org",
  421_614: "https://sepolia.arbiscan.io",
};

export function explorerAddressUrl(chainId: number, address: string): string | null {
  const base = EXPLORERS[chainId];
  if (!base) return null;
  return `${base}/address/${address}`;
}

export function explorerTxUrl(chainId: number, txHash: string): string | null {
  const base = EXPLORERS[chainId];
  if (!base) return null;
  return `${base}/tx/${txHash}`;
}
