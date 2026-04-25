/**
 * Landing placeholder. Phase 0 renders the design tokens visibly so the brand
 * direction is verifiable. DESIGN.md §9.1 specifies the real landing —
 * live stats band, confident headline, two CTAs — which lands in Phase 4.
 */
export default function LandingPage() {
  return (
    <main className="min-h-screen bg-surface-base px-12 py-24 text-fg">
      <header className="mb-24 max-w-4xl">
        <p className="text-fg-muted text-xs uppercase tracking-[0.2em]">
          Phase 0 · scaffold
        </p>
        <h1 className="mt-4 font-display text-5xl font-semibold leading-tight">
          Helios
        </h1>
        <p className="text-fg-secondary mt-3 max-w-2xl text-base leading-relaxed">
          A programmatic capital market for AI trading agents on Kite. One meta-strategy,
          autonomous allocation, ZK-attested trades, cross-chain reputation.
        </p>
      </header>

      <section className="grid grid-cols-2 gap-12 max-w-5xl">
        <TokenSwatch label="Surface base" token="--surface-base" />
        <TokenSwatch label="Surface panel" token="--surface-panel" />
        <TokenSwatch label="Surface elev" token="--surface-elev" />
        <TokenSwatch label="Surface hover" token="--surface-hover" />
        <TokenSwatch label="Amber accent" token="--accent-amber" />
        <TokenSwatch label="Amber bright" token="--accent-amber-bright" />
        <TokenSwatch label="Signal positive" token="--signal-positive" />
        <TokenSwatch label="Signal negative" token="--signal-negative" />
        <TokenSwatch label="Chain · Kite" token="--chain-kite" />
        <TokenSwatch label="Chain · Base" token="--chain-base" />
        <TokenSwatch label="Chain · Arbitrum" token="--chain-arbitrum" />
      </section>

      <section className="mt-24 max-w-4xl">
        <h2 className="font-display text-xs uppercase tracking-[0.2em] text-fg-muted">
          Numerics sample
        </h2>
        <div className="border-subtle mt-4 rounded-md bg-surface-panel p-6">
          <table className="w-full text-sm">
            <thead className="text-fg-muted text-xs uppercase tracking-wider">
              <tr>
                <th className="text-left font-normal pb-3">Strategy</th>
                <th className="text-right font-normal pb-3">NAV</th>
                <th className="text-right font-normal pb-3">P&L %</th>
                <th className="text-right font-normal pb-3">Drawdown</th>
              </tr>
            </thead>
            <tbody className="num">
              <tr className="border-t border-surface-line">
                <td className="py-2 text-fg-secondary">MomentumKite-A</td>
                <td className="py-2 text-right">$1,247.32</td>
                <td className="py-2 text-right text-signal-positive">+1.27%</td>
                <td className="py-2 text-right text-fg-muted">−2.1%</td>
              </tr>
              <tr className="border-t border-surface-line">
                <td className="py-2 text-fg-secondary">MeanRevBase-B</td>
                <td className="py-2 text-right">$987.04</td>
                <td className="py-2 text-right text-signal-negative">−1.30%</td>
                <td className="py-2 text-right text-fg-muted">−4.8%</td>
              </tr>
              <tr className="border-t border-surface-line">
                <td className="py-2 text-fg-secondary">MomentumArb-C</td>
                <td className="py-2 text-right">$1,103.18</td>
                <td className="py-2 text-right text-signal-positive">+3.31%</td>
                <td className="py-2 text-right text-fg-muted">−1.9%</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}

function TokenSwatch({ label, token }: { label: string; token: string }) {
  return (
    <div className="border-subtle flex items-center gap-4 rounded-md bg-surface-panel p-4">
      <span
        className="h-10 w-10 rounded-sm border-subtle"
        style={{ backgroundColor: `var(${token})` }}
      />
      <div>
        <div className="text-fg-primary text-sm">{label}</div>
        <div className="text-fg-muted font-mono text-xs">{token}</div>
      </div>
    </div>
  );
}
