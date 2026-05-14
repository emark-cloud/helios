# Agentic workflow: LLM-driven strategies on Helios

How Helios lets you put a model behind a strategy without rebuilding
the protocol — and what the protocol does to keep the model honest.

This document is for two audiences:

1. **Judges / readers evaluating Kite AI submissions** — read §1 and §2.
2. **Developers shipping their own LLM strategy** — skip to §3.

---

## 1. The shape of the problem

Helios is a programmatic capital market for *autonomous trading agents*.
An allocator routes user capital across competing strategy agents;
every trade carries a Groth16 proof binding it to its declared class;
reputation accrues from realized, attested performance.

The protocol was designed so the strategy agent could be **any
process** — deterministic quant code, a learned policy, or a large
language model. The cryptographic and economic layers don't care.
They care about:

- Does the trade satisfy the class circuit's invariants?
- Does the trade respect the operator's on-chain `paramsHash`?
- Did the operator stake real collateral behind their declared bounds?

If yes to all three, the trade settles. The protocol doesn't know
*how* the signal was generated.

The reference strategies through Phase 6 (momentum, mean-reversion,
yield-rotation) all use deterministic signals. The `llm_momentum_v1`
package fills the obvious gap: a reference implementation where the
**signal source is Claude**, settling against the **same Kite chain
rails as every other strategy**.

## 2. "Claude decides, the chain enforces"

The slogan is also the design.

### What Claude decides

On every bar (60-second default cadence), the strategy runtime calls
`on_bar(asset, snapshot)`. Inside `on_bar`, the strategy calls Claude
via the Anthropic SDK with a structured market context (recent prices,
current position, NAV) and forces a tool-use response:

```python
{
  "action":     "LONG" | "EXIT" | "HOLD",
  "confidence": float in [0, 1],
  "rationale":  str
}
```

Claude is the **signal source**. The strategy is wired up exactly
like a deterministic momentum strategy — same trade shapes, same
SDK helpers, same witness builder, same prover, same executor.

Default model is `claude-haiku-4-5-20251001`; operators can swap to
Sonnet 4.6 or Opus 4.7 for more deliberative decisions. The system
prompt is sent with `cache_control={"type": "ephemeral"}` so cost
stays bounded (~$0.50/day per vault at Haiku, 1-bar cadence).

### What the chain enforces

The vault declares class `momentum_v1`, which means **every trade
goes through the same Groth16 verifier as every other momentum
strategy on Helios.** The circuit (`circuits/momentum_v1.circom`)
enforces six invariants in zero-knowledge:

| # | Invariant | Why |
|---|-----------|-----|
| 1 | `asset_in`, `asset_out` ∈ declared `asset_universe` | LLM can't trade arbitrary tokens |
| 2 | `amount_in ≤ max_position_size` | LLM can't over-allocate |
| 3 | `min_amount_out` respects `max_slippage_bps` | LLM can't tolerate unbounded slippage |
| 4 | Direction matches *some* threshold-consistent signal | LLM can't fabricate signals out of thin air |
| 5 | Trade window respects oracle-attested prices | LLM can't trade against stale data |
| 6 | `block_window_end - block_window_start ≤ 100` | LLM can't backdate trades |

All six are checked by the on-chain `momentum_v1` verifier
(`0x13424B7e…` on Kite testnet) before settlement. A trade that
fails any of them reverts on chain — the LLM literally cannot land
it, no matter what it returns from `on_bar`.

Additionally, the operator's declared bounds are committed in a
Poseidon `paramsHash` and stored in the StrategyRegistry. The hash
binds `(max_position_size_e18, max_slippage_bps, signal_threshold_bps,
stop_loss_price_e18)`. Every `executeWithProof` is checked against
this hash. The LLM operator picks these bounds **once** at deploy
time and stakes 5,000 mUSDC behind them; the model operates inside
that sandbox for the lifetime of the vault.

### Why this is interesting

Most "AI agent that trades" demos collapse one of three things:

- **The agent decides AND executes AND custodies.** No external
  accountability. Lose money = lose audience.
- **The agent decides; humans approve every trade.** Not autonomous.
- **The agent decides; a hand-rolled rule engine post-filters.**
  No cryptographic accountability, no portable reputation, the
  filter is opaque.

Helios collapses none of them. The model has **bounded autonomy**:
- It decides every trade with no human in the loop.
- It signs nothing — the operator's EOA does, after the trade has
  passed the circuit.
- It cannot escape the on-chain bounds because they're enforced by
  Groth16 verification, not by the agent's own code.
- Its track record is **on-chain attested**: every successful trade
  emits `TradeAttested(vault, classId, txHash)`; reputation is
  derived from realized NAV moves on those attested trades.

A user who delegates to this vault is delegating to *a Claude model
operating inside a cryptographically enforced sandbox*. Not to "an
AI that might do anything." The difference is the whole point.

## 3. Build your own

### 3.1 Scaffold

```bash
pip install helios-trader-cli
helios scaffold-strategy llm_momentum_v1 --name MyBot
```

You get a buildable package with the Anthropic SDK already wired,
a working `on_bar`, and an editable `SYSTEM_PROMPT` at the top of
`strategy.py`. The strategy declares `momentum_v1` so it reuses
the existing verifier — no circuit work needed.

### 3.2 Customize

The 90% case is editing the prompt:

```python
SYSTEM_PROMPT = """You are a volatility-aware momentum trader.
LONG only when 10-bar return is positive AND realized volatility is
below the 30-day median. EXIT immediately on signal flip OR on a
3σ adverse move. Be conservative — only fire when confidence > 0.75.
"""
```

The 10% case is supplying your own decision function. The tool-use
schema is fixed (`{action, confidence, rationale}`) so the runtime
contract holds, but the strategy class is yours to modify.

### 3.3 Test offline

```bash
pytest reference-strategies/llm_momentum_v1/tests/
```

The strategy accepts an injected `client` argument; the test suite
uses a `_FakeAnthropic` double so all 17 unit tests run with no API
key and no network. Same pattern works for your own tests.

### 3.4 Backtest

```bash
export ANTHROPIC_API_KEY=sk-ant-...
helios backtest --strategy src/my_bot/strategy.py --period 90d --bar 1h
```

At 1-hour cadence × 90 days × non-USDC assets, expect ~$3 in Haiku
token spend. Swap to `--mock-llm` for a free deterministic dry-run
(planned addition; not in v1).

### 3.5 Deploy

```bash
helios stake top-up --strategy src/my_bot/strategy.py
helios deploy --strategy src/my_bot/strategy.py --target user@host
```

The deploy script packages your strategy as a Docker image, sets
`ANTHROPIC_API_KEY` from your environment, and starts the runtime
on your VPS. The first `TradeAttested` event appears in Goldsky
within one bar of a high-confidence decision firing.

## 4. Where this fits in the v1 protocol

| Layer | What's there | LLM strategy uses |
|---|---|---|
| Circuit | `momentum_v1.circom`, 16 PI, 5.4k constraints | Unchanged — declared class is `momentum_v1` |
| Verifier | `TradeAttestationVerifier` adapter on chain | Unchanged |
| Registry | `StrategyRegistry` with `paramsHashOf` | New entry, same schema |
| Vault | `StrategyVault` proxy + CXR-aware impl | New proxy, existing impl |
| SDK | `helios-strategy-sdk` (`StrategyAgent` base) | Subclassed (`LLMMomentumStrategy`) |
| Runtime | Bar loop, NAV oracle, prover client | Reused verbatim |
| Reputation | `ReputationAnchorV2Bis` | Tracks LLM vault like any other strategy |
| Frontend | `/strategies` page reads Goldsky | Shows LLM vault with class `momentum_v1` |

The only new code is the strategy subclass (~250 LOC including tests)
and a single-vault deploy script. Nothing else in the protocol moves.

That's the test: a useful primitive doesn't require new infrastructure.

## 5. Limits and honest caveats

- **No specialized LLM circuit.** A future class could enforce
  finer-grained model-output invariants (e.g., "rationale entropy >
  threshold", "model id ∈ allowlist"). v1 stops at the existing
  `momentum_v1` bounds because reusing them was the point.
- **Cost scales with vault count, not user count.** Operators pay
  the API bill; users pay the strategy fee. A Sonnet/Opus-backed
  vault is materially more expensive than a Haiku one, and the
  protocol does not currently surface model choice to allocators.
- **Latency budget.** Claude calls add ~1–3s to the bar loop.
  Acceptable at 60s+ bar cadence; not at sub-second.
- **Prompt injection surface.** Market context is structured JSON
  derived from oracle data; an attacker who corrupts the oracle
  could potentially shape model behavior. Mitigated by oracle
  Poseidon commitments (Helios.md §6) but worth naming.

## 6. References

- Spec: `Helios.md` §10 (Strategy Agent SDK)
- Reference impl: `reference-strategies/llm_momentum_v1/`
- Scaffold template: `packages/helios-cli/src/helios_cli/templates/strategy/llm_momentum_v1/`
- Deploy script: `contracts/script/DeployLLMMomentumVault.s.sol`
- Built with Claude Code — see `CLAUDE.md` for the operator guide.
