/**
 * ParamsHash rotation timeline. Closes `TODO.md` line 276 — the
 * audit page reads `ParamsRotation` events to surface every commit
 * that mutated a strategy's canonical paramsHash.
 *
 * Phase-2 reputation engine resets `AgeScore` on each rotation
 * (see `Helios.md §8.7`) so users / allocators care about the
 * boundary as much as the hash itself.
 */

import { explorerTxUrl, formatTimestamp } from "@/lib/format";
import type { ParamsRotationRow } from "@/lib/goldsky";

export function ParamsRotationTimeline({
  chainId,
  rotations,
}: {
  chainId: number;
  rotations: ParamsRotationRow[];
}): JSX.Element {
  if (rotations.length === 0) {
    return (
      <section data-testid="params-rotations">
        <h2 className="mb-2 text-[10px] uppercase tracking-[0.16em] text-fg-muted">
          paramsHash rotations
        </h2>
        <div className="rounded-md border border-surface-line bg-surface-panel p-4 text-center text-xs text-fg-muted">
          No rotations recorded. The strategy still operates on its
          original commit.
        </div>
      </section>
    );
  }

  return (
    <section data-testid="params-rotations">
      <h2 className="mb-2 text-[10px] uppercase tracking-[0.16em] text-fg-muted">
        paramsHash rotations
      </h2>
      <div className="overflow-hidden rounded-md border border-surface-line bg-surface-panel">
        <table className="w-full text-sm">
          <thead className="border-b border-surface-line text-[10px] uppercase tracking-[0.16em] text-fg-muted">
            <tr>
              <th className="px-3 py-2.5 text-left font-normal">When</th>
              <th className="px-3 py-2.5 text-left font-normal">Old hash</th>
              <th className="px-3 py-2.5 text-left font-normal">New hash</th>
              <th className="px-3 py-2.5 text-right font-normal">Tx</th>
            </tr>
          </thead>
          <tbody>
            {rotations.map((r) => (
              <tr key={r.id} className="border-b border-surface-line last:border-b-0">
                <td className="px-3 py-2.5 text-fg-secondary">
                  {formatTimestamp(Number(r.timestamp))}
                </td>
                <td className="px-3 py-2.5 font-mono text-[11px] text-fg-muted" title={r.oldHash}>
                  {trimHash(r.oldHash)}
                </td>
                <td className="px-3 py-2.5 font-mono text-[11px] text-fg-primary" title={r.newHash}>
                  {trimHash(r.newHash)}
                </td>
                <td className="px-3 py-2.5 text-right">
                  <TxLink chainId={chainId} txHash={r.txHash} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function trimHash(hash: string): string {
  if (!hash || hash.length < 10) return hash ?? "—";
  return `${hash.slice(0, 10)}…${hash.slice(-6)}`;
}

function TxLink({ chainId, txHash }: { chainId: number; txHash: string }): JSX.Element {
  const url = explorerTxUrl(chainId, txHash);
  if (!url) return <span className="font-mono text-xs text-fg-muted">{trimHash(txHash)}</span>;
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      className="font-mono text-xs text-fg-muted hover:text-amber"
      title={txHash}
    >
      {trimHash(txHash)}
    </a>
  );
}
