# `llm_momentum_v1` — Claude-driven momentum strategy

A reference Helios strategy where **Claude makes every trade decision** and the
**Kite chain enforces the bounds**. Subclasses `StrategyAgent` with
`declared_class = "momentum_v1"`, so it reuses the existing momentum_v1
Groth16 verifier, witness builder, prover service, and on-chain registry
slot. The only thing that changes is the *signal source*.

## Why this exists

The Helios protocol was designed so that the strategy operator can be any
process — deterministic quant code, a learned policy, or a large language
model. This package demonstrates the LLM case end-to-end:

- **Claude decides** — on every bar, the strategy calls
  `anthropic.messages.create(...)` with the recent price window, current
  position, and NAV. The model returns a structured `decision` tool use:
  `{action: LONG|EXIT|HOLD, confidence: 0..1, rationale: str}`.
- **The chain enforces** — the trade still has to satisfy the
  `momentum_v1` Groth16 circuit and respect the operator's Poseidon
  `paramsHash` (`max_position_size`, `max_slippage_bps`,
  `signal_threshold_bps`, `stop_loss_price`). A hallucinated trade
  outside those bounds simply cannot land.
- **Reputation accrues from outcomes** — the strategy's stake is real
  (5,000 mUSDC), `TradeAttested` events feed the reputation engine,
  realized NAV moves drive the score. No special handling for the LLM —
  the protocol just sees "an agent that posts attested trades."

## Install

```bash
pip install helios-reference-llm-momentum-v1
export ANTHROPIC_API_KEY=sk-ant-...
```

Workspace dev install:

```bash
uv sync                    # from the helios repo root
```

## Library use (10-line drop-in)

```python
from llm_momentum_v1 import LLMMomentumStrategy
from helios.types import MarketSnapshot

s = LLMMomentumStrategy(
    signal_threshold=0.015,        # on-chain bound, not seen by Claude
    lookback_bars=10,
    position_fraction=0.5,
    model="claude-haiku-4-5-20251001",  # or claude-sonnet-4-6 / claude-opus-4-7
    min_confidence=0.6,            # below this, no trade fires
)
s.set_capital(10_000)
intent = s.on_bar("WETH", MarketSnapshot(asset="WETH", ...))
```

## Customize the prompt

```python
from llm_momentum_v1 import LLMMomentumStrategy

MY_PROMPT = """You are a contrarian momentum trader. LONG on dips with
positive 10-bar reversion; EXIT on strength. Be conservative; only fire
when confidence > 0.75."""

s = LLMMomentumStrategy(system_prompt=MY_PROMPT, min_confidence=0.75)
```

The system prompt is sent with `cache_control={"type": "ephemeral"}` — at
1-bar cadence the cache stays warm across roughly 5 bars before expiring,
so cost amortizes well.

## Service mode

```bash
uv run --package helios-reference-llm-momentum-v1 python -m llm_momentum_v1
# FastAPI on :8005 — /v1/, /v1/stats, /health
```

Environment variables follow the `LLM_MOMENTUM_` prefix (see
`service.py:Settings`). Required for live Kite deploys:

| Var | Notes |
|---|---|
| `ANTHROPIC_API_KEY` | Read directly by the Anthropic SDK |
| `LLM_MOMENTUM_ANTHROPIC_MODEL` | Default `claude-haiku-4-5-20251001` |
| `LLM_MOMENTUM_MIN_CONFIDENCE` | Default `0.6` |
| `KITE_RPC_URL`, `ORACLE_ENDPOINT`, `PROVER_ENDPOINT` | Standard Helios surface |
| `STRATEGY_VAULT_ADDRESS` | The deployed `phase6VaultLLMMomentum` proxy |
| `STRATEGY_REGISTRY` | StrategyRegistry V2 (paramsHash committed at startup) |
| `LLM_MOMENTUM_OPERATOR_PK`, `NAV_ORACLE_PK` | Dedicated EOAs per the WS9 pattern |

## Cost ceiling

Haiku at 1-bar cadence (60s), ~2k input tokens / ~200 output tokens per
call ≈ **$0.50 / day per vault**. The strategy *short-circuits* on USDC
(base asset) and bars without enough history, so the actual call volume
is `(asset_universe - {USDC}) × bars / day`. For the default 4-asset
universe that's 3 calls per bar, 4,320 calls/day.

## Failure modes

All of these return `None` (no trade this bar) and log a structured event:

- `ANTHROPIC_API_KEY` missing → `llm_momentum.missing_api_key`
- Anthropic SDK not installed → `llm_momentum.anthropic_not_installed`
- API network error / 5xx → `llm_momentum.api_error`
- Model returned no `tool_use` block → `llm_momentum.no_tool_use`
- Malformed tool input (action ∉ {LONG, EXIT, HOLD}, confidence out of
  range, missing rationale) → `llm_momentum.malformed_tool_input`
- Confidence below `min_confidence` or action == HOLD → `llm_momentum.skip`

This mirrors the `ProverDegraded` skip-bar semantics in
`prover_client.py` — the runtime loop is unchanged.

## Built with Claude Code

The Helios protocol, including this strategy, was built end-to-end in
Claude Code. The development log lives in `TODO.md` at the repo root.
