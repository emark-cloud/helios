"""LLM-driven momentum strategy. Claude decides; the chain enforces.

Subclasses `StrategyAgent` and `declared_class = "momentum_v1"`, so the
existing `momentum_v1` Groth16 verifier, witness builder, prover, and
on-chain registry slot are reused without modification. The only thing
that changes is the *signal*: instead of `recent_return > threshold`,
`on_bar` calls Claude via the Anthropic SDK and turns the model's
tool-use response into a `TradeIntent`.

The model's autonomy is bounded by the on-chain `params_hash` — Poseidon
of `[max_position_size_e18, max_slippage_bps, signal_threshold_bps,
stop_loss_price_e18]`. Every executeWithProof is checked against this
hash, so a hallucinated trade outside the operator's declared bounds
cannot land.

See `Helios.md §10.2` for the class invariants the circuit enforces.
"""

from __future__ import annotations

import json
import os
from typing import Any

import structlog
from helios import Direction, MarketSnapshot, StrategyAgent, TradeIntent
from helios.poseidon import poseidon_hash
from helios.sizing import nav_target_notional

_log = structlog.get_logger(__name__)


DEFAULT_SYSTEM_PROMPT = """You are a momentum trading agent operating on the Helios protocol.

Your job: look at the recent price action for ONE asset and decide whether to
go LONG, EXIT an existing position, or HOLD (do nothing).

Hard bounds (enforced on-chain — you cannot escape these):
- You can only LONG from USDC into the asset, or EXIT the asset back to USDC.
- Max position size and max slippage are committed in the params hash; trade
  amounts and slippage tolerance are set by the runtime, not by you.
- Your only outputs are: action (LONG/EXIT/HOLD), confidence (0..1), rationale.

Decision heuristics (you may override with your own judgement):
- LONG when recent return is positive and momentum is accelerating.
- EXIT when recent return turns negative or momentum stalls while you hold.
- HOLD when the signal is ambiguous — no trade is always a valid choice.

Be honest about confidence. Return confidence < 0.6 if the signal is weak;
the runtime will skip the trade. The protocol rewards realized, attested
performance over time — there is no upside to forcing low-conviction trades.
"""


_DECISION_TOOL: dict[str, Any] = {
    "name": "decision",
    "description": "Emit a trading decision for the current bar.",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["LONG", "EXIT", "HOLD"],
                "description": "LONG to open/add a long, EXIT to close a long, HOLD to skip.",
            },
            "confidence": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "How confident you are in this decision (0..1).",
            },
            "rationale": {
                "type": "string",
                "description": "One sentence on why. Audit-visible.",
            },
        },
        "required": ["action", "confidence", "rationale"],
    },
}


class LLMMomentumStrategy(StrategyAgent):
    """Claude-driven momentum_v1 strategy.

    Reuses the `momentum_v1` circuit + verifier + paramsHash schema.
    The signal source is the only change: an Anthropic API call replaces
    the deterministic `recent_return > threshold` check.
    """

    declared_class = "momentum_v1"
    asset_universe: tuple[str, ...] = ("USDC", "WBTC", "WETH", "WSOL")
    max_position_size_usd = 10_000
    fee_rate_bps = 2_000

    def __init__(
        self,
        signal_threshold: float = 0.015,
        lookback_bars: int = 10,
        max_slippage_bps: int = 30,
        position_fraction: float = 0.5,
        stop_loss_price: float = 0.0,
        asset_universe: tuple[str, ...] | None = None,
        *,
        model: str = "claude-haiku-4-5-20251001",
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        min_confidence: float = 0.6,
        max_tokens: int = 512,
        client: Any | None = None,
    ) -> None:
        super().__init__()
        # `signal_threshold` remains the on-chain bound — the LLM cannot
        # propose a trade whose implied threshold is below this value
        # because the witness builder reuses the same Poseidon commitment.
        self._signal_threshold = signal_threshold
        self._lookback = lookback_bars
        self._max_slippage_bps = max_slippage_bps
        self._position_fraction = position_fraction
        self._stop_loss_price = stop_loss_price
        if asset_universe is not None:
            if not asset_universe or asset_universe[0] != "USDC":
                raise ValueError(
                    "asset_universe must be a non-empty tuple beginning with 'USDC' "
                    f"(got {asset_universe!r})"
                )
            self.asset_universe = tuple(asset_universe)
        self._model = model
        self._system_prompt = system_prompt
        self._min_confidence = min_confidence
        self._max_tokens = max_tokens
        # Lazy-instantiate the Anthropic client so unit tests can inject
        # a mock and import-time `ANTHROPIC_API_KEY` is not required.
        self._client = client

    # ── On-chain params hash (identical to MomentumStrategy) ──
    def params_hash(self) -> bytes:
        max_position_size_e18 = self.max_position_size_usd * 10**18
        signal_threshold_bps = round(self._signal_threshold * 10_000)
        stop_loss_price_e18 = int(self._stop_loss_price * 10**18)
        return poseidon_hash(
            [
                max_position_size_e18,
                self._max_slippage_bps,
                signal_threshold_bps,
                stop_loss_price_e18,
            ]
        ).to_bytes(32, "big")

    # ── Operator surface: ask Claude ───────────────────────────
    def on_bar(self, asset: str, snapshot: MarketSnapshot) -> TradeIntent | None:
        if asset == "USDC":
            return None

        # Need enough history for the prompt to be informative. Mirrors
        # the deterministic strategy's lookback requirement.
        if len(snapshot.prices) < self._lookback + 1:
            return None

        position = self.position_for(asset)
        decision = self._ask_claude(asset, snapshot, position)
        if decision is None:
            return None

        action = decision["action"]
        confidence = float(decision["confidence"])  # _valid_decision guarantees numeric
        if confidence < self._min_confidence or action == "HOLD":
            _log.info(
                "llm_momentum.skip",
                asset=asset,
                action=action,
                confidence=confidence,
                rationale=decision.get("rationale", ""),
            )
            return None

        _log.info(
            "llm_momentum.decision",
            asset=asset,
            action=action,
            confidence=confidence,
            rationale=decision.get("rationale", ""),
            model=self._model,
        )

        if action == "LONG" and position <= 0:
            return TradeIntent(
                asset_in="USDC",
                asset_out=asset,
                amount_in_usd=self._size(),
                direction=Direction.LONG,
                max_slippage_bps=self._max_slippage_bps,
                is_nav_targeted=True,
            )

        if action == "EXIT" and position > 0:
            return TradeIntent(
                asset_in=asset,
                asset_out="USDC",
                amount_in_asset=position,
                direction=Direction.EXIT,
                max_slippage_bps=self._max_slippage_bps,
                is_signal_flip=True,
            )

        # LONG-while-long or EXIT-while-flat: nothing to do.
        return None

    # ── Claude call ───────────────────────────────────────────
    def _ask_claude(
        self,
        asset: str,
        snapshot: MarketSnapshot,
        position: float,
    ) -> dict[str, Any] | None:
        client = self._get_client()
        if client is None:
            return None

        recent = snapshot.prices[-(self._lookback + 1) :]
        latest = recent[-1]
        oldest = recent[0]
        ret = (latest - oldest) / oldest if oldest else 0.0
        vol = _stddev(recent) if len(recent) > 1 else 0.0

        context = {
            "asset": asset,
            "current_price": latest,
            "lookback_bars": self._lookback,
            "lookback_return_pct": round(ret * 100, 4),
            "lookback_stddev": round(vol, 6),
            "recent_prices_oldest_to_newest": [round(p, 6) for p in recent],
            "current_position_qty": position,
            "nav_usd": round(self.nav, 2),
            "max_position_size_usd": self.max_position_size_usd,
        }

        try:
            response = client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=[
                    {
                        "type": "text",
                        "text": self._system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    },
                ],
                tools=[_DECISION_TOOL],
                tool_choice={"type": "tool", "name": "decision"},
                messages=[{"role": "user", "content": json.dumps(context)}],
            )
        except Exception as exc:
            _log.warning("llm_momentum.api_error", asset=asset, err=str(exc))
            return None

        for block in getattr(response, "content", []) or []:
            block_type = getattr(block, "type", None)
            if block_type != "tool_use":
                continue
            tool_input = getattr(block, "input", None)
            if not isinstance(tool_input, dict):
                continue
            if not _valid_decision(tool_input):
                _log.warning(
                    "llm_momentum.malformed_tool_input",
                    asset=asset,
                    tool_input=tool_input,
                )
                return None
            return tool_input

        _log.warning("llm_momentum.no_tool_use", asset=asset)
        return None

    def _get_client(self) -> Any | None:
        if self._client is not None:
            return self._client
        try:
            import anthropic
        except ImportError:
            _log.error(
                "llm_momentum.anthropic_not_installed",
                hint="pip install anthropic>=0.40",
            )
            return None
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            _log.error("llm_momentum.missing_api_key", env_var="ANTHROPIC_API_KEY")
            return None
        self._client = anthropic.Anthropic(api_key=api_key)
        return self._client

    # ── Sizing (identical to MomentumStrategy._size) ──────────
    def _size(self) -> float:
        return nav_target_notional(self, self._position_fraction)

    # ── Test/runtime helpers ──────────────────────────────────
    def set_capital(self, usd: float) -> None:
        self._set_capital(usd)
        self._set_nav(usd)

    def set_position(self, asset: str, qty: float, avg_price: float, direction: Direction) -> None:
        self._set_position(asset, qty, avg_price, direction)

    @property
    def signal_threshold(self) -> float:
        """Exposed for the witness builder — the LLM doesn't see this."""
        return self._signal_threshold

    @property
    def lookback_bars(self) -> int:
        return self._lookback

    @property
    def model(self) -> str:
        return self._model


def _valid_decision(payload: dict[str, Any]) -> bool:
    if payload.get("action") not in {"LONG", "EXIT", "HOLD"}:
        return False
    raw_conf = payload.get("confidence")
    if not isinstance(raw_conf, (int, float)):
        return False
    confidence = float(raw_conf)
    if not 0.0 <= confidence <= 1.0:
        return False
    if not isinstance(payload.get("rationale"), str):
        return False
    return True


def _stddev(xs: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    mean = sum(xs) / n
    var = sum((x - mean) ** 2 for x in xs) / (n - 1)
    return var**0.5
