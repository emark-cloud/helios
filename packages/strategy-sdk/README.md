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
