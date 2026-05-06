# helios-strategy-sdk

Public SDK for shipping a trading strategy on the Helios marketplace.

```bash
pip install helios-strategy-sdk
```

## Minimal example

```python
from helios import StrategyAgent, MarketSnapshot, TradeIntent, Direction


class MyMomentumStrategy(StrategyAgent):
    declared_class = "momentum_v1"
    asset_universe = ["BTC", "ETH", "SOL", "BNB"]
    max_position_size_usd = 10_000
    fee_rate_bps = 2000  # 20%

    def __init__(self) -> None:
        super().__init__()
        self.signal_threshold = 0.015
        self.lookback_bars = 10

    def on_bar(self, asset: str, snapshot: MarketSnapshot) -> TradeIntent | None:
        recent = snapshot.return_over(bars=self.lookback_bars)
        if recent > self.signal_threshold and self.position_for(asset) <= 0:
            return TradeIntent(
                asset_in="USDC",
                asset_out=asset,
                amount_in_usd=min(5_000, self.available_capital * 0.5),
                direction=Direction.LONG,
                max_slippage_bps=30,
            )
        return None
```

The SDK handles market data polling, proof generation, on-chain submission,
NAV reporting, and fee distribution. Operators implement only the signal logic.

See [`Helios.md §10`](../../Helios.md) for the full SDK contract and the list
of supported strategy classes.

## Scaffold a strategy

The companion `helios` CLI scaffolds a runnable strategy in one command —
the package depends only on `helios-strategy-sdk` from public PyPI, so an
AI coding agent can iterate on the signal without touching any Helios
internals.

```bash
pip install helios-trader-cli  # ships the `helios` binary
helios scaffold-strategy momentum_v1 --name "MyMomentum" --target-dir ./my-mom
cd ./my-mom && pip install -e .
helios backtest --strategy src/my_momentum/strategy.py --period 90d
```

The scaffold ships per-class templates for `momentum_v1`,
`mean_reversion_v1`, and `yield_rotation_v1`. Each one is a single editable
signal file plus a `pyproject.toml`, `Dockerfile`, and `.env.example` so
the path from local backtest → Kite testnet registration → VPS deploy is
the same three commands every time.

## Build with Claude Code

This SDK and the `helios scaffold-strategy` command are designed so an AI
coding agent can author and ship a complete trading strategy without
modifying any Helios code. The scaffold's per-class templates encode the
on-chain invariants and signal-shape conventions; Claude Code only has
to fill in the body of `on_bar` (or `propose_rotation` for
`yield_rotation_v1`).

In your terminal:

```bash
helios scaffold-strategy momentum_v1 --name "MyMomentum" --target-dir ./my-mom
cd ./my-mom

claude "Open src/my_momentum/strategy.py and rewrite on_bar to use a \
20-bar lookback and a 2.5% threshold, with an EMA-crossover exit. \
Then run 'helios backtest --strategy src/my_momentum/strategy.py \
--period 90d' and report the Sharpe ratio + max drawdown."
```

The repo's [`CLAUDE.md`](https://github.com/emark-cloud/helios/blob/main/CLAUDE.md)
is the canonical operational guide for AI agents working on Helios; class
invariants and circuit-bound bounds live in [`Helios.md §10`](../../Helios.md).
