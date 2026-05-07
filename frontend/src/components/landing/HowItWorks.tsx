/**
 * Landing — three-act mechanism strip. DESIGN.md §8.4 (make the
 * two-sided market legible) and §9.1 (the landing must communicate
 * what is different in 10 seconds). Editorial, not promotional —
 * declarative copy, no icons, no emoji, no marketing voice.
 */

export function HowItWorks(): JSX.Element {
  const phases: Array<{ n: string; title: string; body: string }> = [
    {
      n: "01",
      title: "You set the rules",
      body: "Pick a template or customize the policy: how much to deploy, which assets, your max drawdown, your fee ceiling. One signature commits the rules on-chain.",
    },
    {
      n: "02",
      title: "An allocator routes capital",
      body: "Your chosen allocator agent picks the best AI strategies for those rules and rebalances as performance changes — autonomously, within the bounds you signed.",
    },
    {
      n: "03",
      title: "Every trade carries a proof",
      body: "Strategies submit a zero-knowledge proof with each trade, binding it to the class they declared. A momentum agent literally cannot execute a yield rotation.",
    },
  ];

  return (
    <section className="flex flex-col gap-6">
      <div className="flex items-baseline justify-between border-b border-surface-line pb-2">
        <h2 className="font-mono text-[12px] uppercase tracking-[0.28em] text-fg-muted">
          How it works
        </h2>
        <span className="font-mono text-[12px] uppercase tracking-[0.18em] text-fg-muted">
          Three movements
        </span>
      </div>
      <div className="grid gap-px overflow-hidden rounded-md border border-surface-line bg-surface-line lg:grid-cols-3">
        {phases.map((p) => (
          <article
            key={p.n}
            className="flex flex-col gap-4 bg-surface-panel px-6 py-7 lg:px-7 lg:py-8"
          >
            <span
              aria-hidden
              style={{
                fontFamily: "var(--font-serif)",
                fontStyle: "italic",
                fontSize: "clamp(2.75rem, 5.5vw, 4rem)",
                lineHeight: 0.92,
                color: "var(--fg-secondary)",
                letterSpacing: "-0.02em",
              }}
            >
              {p.n}
              <span style={{ color: "var(--accent-amber)" }}>.</span>
            </span>
            <h3 className="font-display text-base font-semibold text-fg-primary">
              {p.title}
            </h3>
            <p className="text-sm leading-relaxed text-fg-secondary">{p.body}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
