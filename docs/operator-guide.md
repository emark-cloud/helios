# Helios — Strategy operator guide

End-to-end how-to for shipping a strategy on Helios. From an empty
folder to an on-chain registered, capital-eligible strategy in one
session.

This guide assumes you have:

- Python 3.11+
- A funded operator key on Kite testnet (chain id `2368`) or mainnet
  (`2366`) with USDC for stake
- Access to a running Helios prover service (`PROVER_URL`)

The Helios CLI does the heavy lifting. You write one file
(`my_strategy.py`), the CLI handles backtesting, packaging, deployment,
stake management, and proof round-trips.

---

## 0. Install

```bash
pip install helios-strategy-sdk      # the SDK you'll subclass
pip install helios-cli               # backtest + deploy + stake commands
```

Both are published to PyPI (test-PyPI today, real PyPI at Phase 4
launch). Pin a major version once you're in production:
`helios-strategy-sdk>=0.1,<0.2`.

---

## 1. Write the strategy

Subclass `helios.StrategyAgent` and override `on_bar`. That's it — the
SDK supplies sensible defaults for sizing, exits, and manifest
construction. See `Helios.md §10` for the full contract.

```python
# my_strategy.py
from helios import Direction, StrategyAgent, TradeIntent


class MyMomentum(StrategyAgent):
    declared_class = "momentum_v1"      # circuit class your trades prove against
    asset_universe = ("USDC", "WKITE", "WETH")
    max_position_size_usd = 5_000
    fee_rate_bps = 2_000                 # 20% performance fee above HWM

    def on_bar(self, asset, snapshot):
        if asset == "USDC":              # base asset never trades
            return None
        ret = snapshot.return_over(bars=10)
        position = self.position_for(asset)
        if ret > 0.015 and position <= 0:
            return TradeIntent(
                asset_in="USDC",
                asset_out=asset,
                amount_in_usd=min(self.max_position_size_usd, self.available_capital * 0.5),
                direction=Direction.LONG,
                max_slippage_bps=30,
            )
        if ret < -0.015 and position > 0:
            return TradeIntent(
                asset_in=asset,
                asset_out="USDC",
                amount_in_asset=position,
                direction=Direction.EXIT,
                max_slippage_bps=30,
            )
        return None
```

The class declares its own `declared_class` — `momentum_v1`,
`mean_reversion_v1`, or `yield_rotation_v1`. Pick the one whose circuit
your `on_bar` logic respects; the on-chain verifier rejects mismatched
trades.

---

## 2. Backtest

Run the SDK's synthetic-bar engine and write a markdown report under
`docs/backtests/<class>/`:

```bash
helios backtest --strategy ./my_strategy.py --period 90d
```

Output:

```
Bars:           2160
Initial:        $10,000.00
Final NAV:      $10,742.15
Total return:   +7.42%
Sharpe (ann.):  1.34
Max drawdown:   4.21%
Realized P&L:   $+742.15
Trades:         18
Win rate:       66.7%

Report: docs/backtests/momentum_v1/my_strategy_90d.md
```

Periods supported: `7d`, `30d`, `90d`, `180d`. Reports include a
NAV-path ASCII chart and the full set of `BacktestReport` fields. The
seed defaults to `42` — pass `--seed N` to explore alternate paths.

---

## 3. Simulate (CI smoke)

`helios simulate` runs the same engine over a much shorter horizon
with per-bar progress prints. Use it as a smoke test in CI:

```bash
helios simulate --strategy ./my_strategy.py --minutes 60
```

Deterministic; finishes in <1 sec on typical hardware. A `helios
simulate` step in your CI catches `on_bar` regressions before you
re-run the full backtest.

---

## 4. Test the proof round-trip

Before you submit any real capital, prove that your trades will
verify on-chain. Build a trade spec — a JSON file with the witness
inputs your circuit class expects:

```json
{
  "strategyClass": "momentum_v1",
  "declaredClass": "momentum_v1",
  "witnessInputs": {
    "max_position_size": "5000000000000000000",
    "max_slippage_bps": "50",
    "signal_threshold": "100",
    "stop_loss_price": "0",
    "price_observations": ["1000", "1005", "1010", "..."]
  }
}
```

(See `reference-strategies/momentum_v1/src/momentum_v1/witness.py`
and `circuits/momentum_v1.circom` for the exact field set.)

Then:

```bash
helios test-proof --trade ./trade.json \
    --rpc-url https://rpc-testnet.gokite.ai
```

The CLI POSTs to the prover, packs the returned snarkjs proof into
the 256-byte form `TradeAttestationVerifier.verify` accepts, and
read-calls the verifier. Exit code 0 means your proof is on-chain
ready.

CI mode (no RPC required):

```bash
helios test-proof --trade ./trade.json --skip-onchain
```

---

## 5. Deploy to a VPS

`helios deploy` packages your single-file strategy into a Docker
container and ships it to a VPS. Defaults to dry-run so you can
review the plan first:

```bash
helios deploy --strategy ./my_strategy.py --vps helios@vps.example
```

Once the plan looks right, apply it:

```bash
helios deploy --strategy ./my_strategy.py --vps helios@vps.example --execute
```

The deploy uses `templates/Dockerfile.strategy` shipped inside the
CLI. Custom Python deps go in a `requirements.extra.txt` next to
your strategy file:

```bash
helios deploy \
    --strategy ./my_strategy.py \
    --vps helios@vps.example \
    --requirements ./requirements.extra.txt \
    --execute
```

The container is named `helios-strategy` by default and registered
with `--restart unless-stopped` — survives reboots, restarts on
crash. Override with `--container-name` and `--image-tag` if you run
multiple strategies side-by-side on one VPS.

---

## 6. Register and stake

Registration happens via `StrategyRegistry.registerStrategy(...)`,
called once when you first deploy your strategy vault. From there,
the CLI manages your stake:

```bash
# Top up stake (USDC base units — 1 USDC = 1_000_000)
helios stake top-up \
    --strategy-id 0xYourStrategyVault \
    --amount 1000000000 \
    --rpc-url https://rpc-testnet.gokite.ai \
    --operator-pk $OPERATOR_PK
```

The CLI reads the `StrategyRegistry` and `USDC` addresses from
`contracts/deployments/<chain>.json` automatically — pass `--chain`
to switch between `kite-testnet`, `kite-mainnet`, etc.

`top-up` issues two transactions:
1. `USDC.approve(StrategyRegistry, amount)`
2. `StrategyRegistry.topUpStake(strategyId, amount)`

Both tx hashes are printed on success. To withdraw:

```bash
helios stake initiate-withdrawal --strategy-id 0xYourStrategyVault --amount 500000000
# wait for the cooldown window (see Helios.md §6)
helios stake claim-withdrawal --strategy-id 0xYourStrategyVault
```

Use `--dry-run` on any stake command to print the planned tx without
submitting.

---

## 7. Watch your reputation

Once the strategy is registered + staked + executing trades, the
reputation engine ingests your fills (and the cohort's) and posts
score updates to `ReputationAnchor`. Read your current score and the
five §8.2 components at:

- **Strategy detail page:** `https://helios.gokite.ai/s/<strategyId>`
- **Audit page (raw inputs):** `https://helios.gokite.ai/audit/<strategyId>`

Trade quality, drawdown, capital efficiency, and consistency all
feed in — see `docs/reputation-math.md` for the formula.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `helios backtest` exits with `no StrategyAgent subclass` | Your file imports `StrategyAgent` but doesn't subclass it. | Define `class MyStrategy(StrategyAgent): ...`. |
| `helios test-proof` returns 503 from prover | Witness inputs don't satisfy circuit constraints (e.g., `block_window > 100`). | Re-check the circuit's invariants in `circuits/<class>.circom`. |
| `helios test-proof` says `verifier REJECTED` | Proof was generated but on-chain `Verifier` says no. | Almost always means the wrong `declaredClass` for the circuit. Match them up. |
| `helios stake top-up` tx reverts at `ERC20InsufficientAllowance` | Auto-approve race or you're using a non-standard USDC. | Set `--usdc 0x...` explicitly to the USDC token your registry expects. |
| `helios deploy --execute` hangs | Your VPS doesn't trust your local SSH key. | `ssh-copy-id helios@vps.example` first, then re-run. |

---

## Reference strategies

The three reference strategies in `reference-strategies/` are
production-grade examples — full runtime loops, prover client,
on-chain submission. Read them when you're ready to graduate from a
single-file strategy:

- `reference-strategies/momentum_v1/` — momentum signal + EXIT-on-flip
- `reference-strategies/mean_reversion_v1/` — Bollinger-band reversion
- `reference-strategies/yield_rotation_v1/` — cross-pool rotation
