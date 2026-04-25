# helios-allocator-sdk

Public SDK for shipping a competing allocator on the Helios marketplace. The reference
allocator (Sentinel) and the second reference (Helix) are both built on this SDK.

```bash
pip install helios-allocator-sdk
```

## Minimal example

```python
from helios_allocator import (
    BaseAllocator,
    MetaStrategy,
    StrategyCandidate,
    AllocationTarget,
)


class VolAdjustedAllocator(BaseAllocator):
    name = "VolatilityAware"
    fee_rate_bps = 500  # 5%
    supported_classes = ["momentum_v1", "mean_reversion_v1", "yield_rotation_v1"]

    def rank_strategies(
        self,
        user: MetaStrategy,
        candidates: list[StrategyCandidate],
    ) -> list[float]:
        scores: list[float] = []
        for c in candidates:
            base = c.reputation_score * c.capacity_factor * c.fee_fit(user.max_fee_rate_bps)
            vol_penalty = 1.0 / (1.0 + c.realized_volatility_30d * 5.0)
            scores.append(base * vol_penalty)
        return scores

    def allocate(
        self,
        user: MetaStrategy,
        ranked: list[StrategyCandidate],
        capital: int,
    ) -> list[AllocationTarget]:
        return self.default_top_k_allocation(user, ranked, capital)
```

The SDK handles capital deployment, drawdown monitoring, fee crystallization,
defund triggers, Goldsky reads, ReputationAnchor writes, and Docker packaging.
Operators implement the ranking + allocation logic.

See [`Helios.md §11`](../../Helios.md) for the full SDK contract.
