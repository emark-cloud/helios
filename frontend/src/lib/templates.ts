/**
 * Onboarding meta-strategy templates. The three options at /onboard
 * (DESIGN.md §9.2) each express a different point on the
 * caution/upside curve. Customization on top of a template is allowed
 * but not encouraged — the templates are the calibrated defaults.
 *
 * Keep these tuned to the Phase 1 capacity story: only momentum is
 * live as a strategy class today, but the meta-strategy schema accepts
 * the others so users don't need to re-onboard once mean-reversion +
 * yield-rotation flip on in Phase 2.
 */

import type { MetaStrategyPayload } from "./sentinel";

export type TemplateKey = "conservative" | "balanced" | "aggressive";

export type TemplateForm = Omit<
  MetaStrategyPayload,
  "user_address" | "valid_until" | "nonce" | "signature"
>;

/**
 * Defund knobs are surfaced in `CustomizationPanel` and consumed by
 * `formToContractStruct` for the on-chain MetaStrategy. They are
 * intentionally **not** part of `MetaStrategyPayload` — Sentinel's REST
 * shape doesn't track them; only the chain enforces.
 *
 * `MetaStrategyLib` substitutes its defaults when the caller passes
 * zero, so leaving the user on `0/0/0` is the "use defaults" path.
 */
export type DefundForm = {
  defund_twap_bars: number;
  defund_bond_bps: number;
  defund_confirm_blocks: number;
};

/** Per-template defund presets. Conservative is tighter, aggressive
 *  looser, balanced lines up with `MetaStrategyLib` defaults. */
export const DEFUND_PRESETS: Record<TemplateKey, DefundForm> = {
  conservative: { defund_twap_bars: 5, defund_bond_bps: 75, defund_confirm_blocks: 40 },
  balanced: { defund_twap_bars: 3, defund_bond_bps: 50, defund_confirm_blocks: 25 },
  aggressive: { defund_twap_bars: 2, defund_bond_bps: 25, defund_confirm_blocks: 15 },
};

export type Template = {
  key: TemplateKey;
  label: string;
  blurb: string;
  form: TemplateForm;
};

const ALL_CLASSES = ["momentum_v1", "mean_reversion_v1", "yield_rotation_v1"];
const PHASE1_ASSETS = ["BTC", "ETH", "SOL"];
const KITE_CHAIN = 2368;

export const TEMPLATES: Record<TemplateKey, Template> = {
  conservative: {
    key: "conservative",
    label: "Conservative",
    blurb:
      "Tight drawdown, slow rebalance, momentum-only. Fewer strategies, smaller positions, lower fee tolerance.",
    form: {
      allowed_strategy_classes: ["momentum_v1"],
      allowed_assets: PHASE1_ASSETS,
      allowed_chains: [KITE_CHAIN],
      max_capital_usd: 1_000,
      max_per_strategy_bps: 2_500, // 25%
      max_strategies_count: 4,
      drawdown_threshold_bps: 1_000, // 10%
      max_fee_rate_bps: 300, // 3%
      rebalance_cadence_sec: 3_600, // 1h
      // Cold-start: conservative users still seed the long tail, but at
      // half the default share — fresh strategies are riskier per
      // Helios.md §8.7.
      bootstrap_share_bps: 500, // 5%
      min_attested_trades: 50,
    },
  },
  balanced: {
    key: "balanced",
    label: "Balanced",
    blurb:
      "Moderate drawdown, mixed classes, default for first-time users. Tracks the demo path in Helios.md §14.1.",
    form: {
      allowed_strategy_classes: ALL_CLASSES,
      allowed_assets: PHASE1_ASSETS,
      allowed_chains: [KITE_CHAIN],
      max_capital_usd: 1_000,
      max_per_strategy_bps: 3_500, // 35%
      max_strategies_count: 5,
      drawdown_threshold_bps: 1_500, // 15%
      max_fee_rate_bps: 500, // 5%
      rebalance_cadence_sec: 1_800, // 30m
      bootstrap_share_bps: 1_000, // 10%
      min_attested_trades: 50,
    },
  },
  aggressive: {
    key: "aggressive",
    label: "Aggressive",
    blurb:
      "Wider drawdown band, faster rebalance, higher fee ceiling. For users who want the system to chase reputation aggressively.",
    form: {
      allowed_strategy_classes: ALL_CLASSES,
      allowed_assets: PHASE1_ASSETS,
      allowed_chains: [KITE_CHAIN],
      max_capital_usd: 1_000,
      max_per_strategy_bps: 5_000, // 50%
      max_strategies_count: 6,
      drawdown_threshold_bps: 2_500, // 25%
      max_fee_rate_bps: 800, // 8%
      rebalance_cadence_sec: 900, // 15m
      // Aggressive users seed the long tail more heavily — bigger
      // bootstrap share, smaller graduation gate.
      bootstrap_share_bps: 1_500, // 15%
      min_attested_trades: 30,
    },
  },
};
