# Helios — Allocator operator guide

End-to-end how-to for shipping a competing allocator on Helios. From
an empty folder to an on-chain registered, capital-eligible allocator
in one session.

This guide assumes you have:

- Python 3.11+
- A funded operator key on Kite testnet (chain id `2368`) or mainnet
  (`2366`) with USDC for stake
- Access to a Goldsky read endpoint (`GOLDSKY_ENDPOINT`) and a Kite
  RPC (`KITE_RPC_URL`)

The Helios CLI does the heavy lifting. You write one file
(`my_allocator.py` — or the `BaseAllocator` subclass scaffolded by
`helios-allocator init`), the SDK runtime handles the six-step
decision loop, drawdown enforcement, fee crystallization, on-chain tx
submission, and dashboard event emission. You only own ranking and
allocation.

Sibling guide: `docs/operator-guide.md` covers the *strategy* surface
(strategies are what allocators allocate *to*). The two surfaces share
a CLI binary and a deployment story; the contracts they touch are
different.

---

## 0. Install

```bash
pip install helios-allocator-sdk      # the SDK you'll subclass
pip install helios-trader-cli         # provides `helios-allocator` (and `helios`)
```

Both are distributed via GitHub Releases of the `helios` repo today
(see `docs/external-contributor/README.md` for a one-line
`--find-links` install) and via test-PyPI for `helios-allocator-sdk`;
the CLI joins test-PyPI once its trusted-publisher entry is
registered. Real PyPI publishing lands at Phase 4. Pin a major version
once you're in production: `helios-allocator-sdk>=0.1,<0.2`.

The CLI's PyPI dist name is `helios-trader-cli` — the `helios-allocator`
binary is the entry point declared in
`packages/helios-cli/pyproject.toml:25`.

---

## 1. Scaffold the project

```bash
helios-allocator init --name "Acme Allocator" --target-dir ./acme-allocator
```

The scaffold drops a runnable Python project under `./acme-allocator`
with a Sentinel-style baseline ranker pre-wired. The `Helios *`
namespace is reserved on-chain — `init` rejects names matching that
prefix client-side so you don't burn a tx on a guaranteed
`AllocatorRegistry` revert (`packages/helios-cli/src/helios_cli/allocator.py:46`,
`contracts/src/AllocatorRegistry.sol:63`).

Layout:

```
acme-allocator/
├── pyproject.toml
├── Dockerfile               # produced by `helios-allocator deploy`
├── .env.example
└── src/
    └── acme_allocator/
        ├── __init__.py
        ├── __main__.py      # boots the SDK runtime
        └── allocator.py     # your BaseAllocator subclass
```

> **Note:** the scaffolded `__main__.py` constructs an `AllocatorLoop`
> with a `LoopConfig` shape (`rpc_url`, `goldsky_endpoint`,
> `allocator_pk`, `allocator_vault`, `tick_interval_sec`) that does
> not match the actual SDK signature
> (`packages/allocator-sdk/src/helios_allocator/runtime/loop.py:57`,
> which takes `drawdown_check_interval_sec`,
> `rank_update_interval_sec`, `fee_check_interval_sec`, and requires a
> pre-constructed `AllocatorStore`, `AllocatorGoldsky`, and
> `AllocatorOnChain`). `loop.run_forever()` does not exist either.
> Until the scaffold catches up, the canonical wiring lives in
> `services/sentinel/src/sentinel/service.py:96-122` — copy that
> `build_app` body verbatim into your `__main__.py`.

---

## 2. Implement `rank_strategies` and `allocate`

Subclass `helios_allocator.BaseAllocator` and override the two abstract
methods. That's the entire allocator surface — everything else is loop
machinery the SDK supplies.

```python
# src/acme_allocator/allocator.py
from helios_allocator import (
    AllocationTarget,
    BaseAllocator,
    MetaStrategy,
    StrategyCandidate,
)


class AcmeAllocator(BaseAllocator):
    name = "Acme Allocator"
    fee_rate_bps = 500                 # 5% on user net realized profit above HWM
    supported_classes = ("momentum_v1", "mean_reversion_v1", "yield_rotation_v1")

    def rank_strategies(
        self,
        user: MetaStrategy,
        candidates: list[StrategyCandidate],
    ) -> list[float]:
        return [self._score(c, user) for c in candidates]

    def allocate(
        self,
        user: MetaStrategy,
        ranked: list[StrategyCandidate],
        capital: int,
    ) -> list[AllocationTarget]:
        if capital <= 0 or not ranked:
            return []
        scores = self.rank_strategies(user, ranked)
        eligible = [(c, s) for c, s in zip(ranked, scores, strict=True) if s > 0]
        eligible = eligible[: user.max_strategies_count]
        if not eligible:
            return []
        candidates = [c for c, _ in eligible]
        sub_scores = [s for _, s in eligible]
        return self.score_weighted_allocation(user, candidates, capital, scores=sub_scores)

    def _score(self, c: StrategyCandidate, user: MetaStrategy) -> float:
        # Differentiate me. Sentinel's product is the baseline; you only
        # ship if your function beats it on user outcomes.
        fee_ok = 1.0 if c.fee_rate_bps <= user.max_fee_rate_bps else 0.0
        return (
            c.reputation_score
            * c.capacity_factor()
            * c.class_fit(user.allowed_strategy_classes)
            * fee_ok
        )
```

The class declares its `fee_rate_bps` and `supported_classes` —
`AllocatorRegistry.registerAllocator` consumes both as part of your
on-chain manifest. Names matching `Helios *` revert at registration
(`contracts/src/AllocatorRegistry.sol:63`).

---

## 3. The `BaseAllocator` interface

Verbatim from
`packages/allocator-sdk/src/helios_allocator/base.py:26-58`:

```python
class BaseAllocator(ABC):
    name: ClassVar[str] = ""
    fee_rate_bps: ClassVar[int] = 0
    supported_classes: ClassVar[Sequence[str]] = ()

    @abstractmethod
    def rank_strategies(
        self,
        user: MetaStrategy,
        candidates: list[StrategyCandidate],
    ) -> list[float]:
        """Return one score per candidate. Higher is better."""

    @abstractmethod
    def allocate(
        self,
        user: MetaStrategy,
        ranked: list[StrategyCandidate],
        capital: int,
    ) -> list[AllocationTarget]:
        """Convert a ranked list (best → worst) into concrete allocation targets."""
```

Two helpers on `BaseAllocator` cover the common allocation shapes:

| Helper | Behavior |
|---|---|
| `default_top_k_allocation(user, ranked, capital)` | Take top-K by `user.max_strategies_count`, even split, capped per-strategy at `user.max_per_strategy_bps`. |
| `score_weighted_allocation(user, selected, capital, scores=...)` | Weight each selected candidate by `max(0, score) / total`. Same per-strategy cap. Pass `scores` if you've already ranked — omitting it triggers an O(n²) re-rank inside the helper. |

### Decision lifecycle (`Helios.md §11.2`)

The SDK's `AllocatorLoop` runs the six-step cycle on a single tick
coordinator gated at `drawdown_check_interval_sec` (60s default —
`packages/allocator-sdk/src/helios_allocator/runtime/loop.py:57`):

1. **Discover & rank** — Goldsky directory pulled on
   `rank_update_interval_sec` (300s default), passed through your
   `rank_strategies`.
2. **Compute target** — your `allocate(user, ranked, capital)`
   yields a list of `AllocationTarget` rows.
3. **Diff target against current** — per-strategy capital deltas
   (`runtime/loop.py:431-451`).
4. **Drawdown check (highest priority)** — every live allocation's
   TWAP drawdown is compared against `user.drawdown_threshold_bps`;
   breaches fire `defundStrategy` before any rebalance applies.
5. **Apply diffs** — pure redistribution batches into a single
   `AllocatorVault.rebalance(...)` call; full removals or
   idle-bound shrinkage take the per-op `defundStrategy` path
   (`runtime/loop.py:219-336`).
6. **Fee crystallization** — opportunistic; when `nav_usd ≥ HWM × (1 + 5%)`
   the loop calls `settleStrategyFee` (`runtime/loop.py:386-407`,
   `FEE_THRESHOLD_BPS = 500`).

### Inputs you receive

`MetaStrategy`
(`packages/allocator-sdk/src/helios_allocator/types.py:17-37`) — the
user's signed allocation policy mirrored from `UserVault`:
`allowed_strategy_classes`, `allowed_assets`, `allowed_chains`,
`max_capital_usd`, `max_per_strategy_bps`, `max_strategies_count`,
`drawdown_threshold_bps`, `max_fee_rate_bps`, `rebalance_cadence_sec`,
`bootstrap_share_bps` (`Helios.md §8.7`), and `min_attested_trades`.

`StrategyCandidate`
(`packages/allocator-sdk/src/helios_allocator/types.py:40-70`) — one
row per eligible strategy: `declared_class`, `chain_id`, `operator`,
`fee_rate_bps`, `stake_amount_usd`, `max_capacity_usd`,
`current_allocations_usd`, `reputation_score`,
`realized_volatility_30d`, `sharpe_30d`, `max_drawdown_30d_bps`,
`trades_attested`. Three ratio helpers ride on the type:
`capacity_factor()`, `fee_fit(max_fee)`, `class_fit(allowed)`.

### Output you emit

`AllocationTarget`
(`packages/allocator-sdk/src/helios_allocator/types.py:73-80`):
`(strategy_id, chain_id, capital_usd, weight_bps)`. The runtime sums
per-strategy capital and rejects any plan where weight bps overflow
10,000.

---

## 4. Onchain registration

Registration happens via `AllocatorRegistry.registerAllocator(...)` —
verbatim signature from
`contracts/src/AllocatorRegistry.sol:69-76`:

```solidity
function registerAllocator(
    string calldata name,
    address operatorVault,
    bytes32 rankingFunctionHash,
    bytes32[] calldata supportedClasses,
    uint16 feeRateBps,
    uint256 stakeAmount
) external nonReentrant returns (address allocatorId);
```

Stake is denominated in the registry's `stakeToken` (USDC on Kite
testnet/mainnet — see `contracts/deployments/kite-testnet.json`). The
caller transfers `stakeAmount` of USDC into the registry in the same
tx; the operator EOA (`msg.sender`) becomes the only address allowed
to call `initiateStakeWithdrawal`, `completeStakeWithdrawal`, and
`deactivate` (`AllocatorRegistry.sol:131-170`).

The §5.3 reference allocator persona stakes **$10,000 USDC**
(`Helios.md §5.3` step 4); use that as your baseline. Stake size is
log-curve weighted in the allocator reputation formula (see §5
below), so stake is barrier-to-entry, not skill — go higher only if
your fee strategy depends on early ranking visibility.

The SDK exposes a one-shot helper that wraps the call —
`AllocatorOnChain.register_allocator(...)`
(`packages/allocator-sdk/src/helios_allocator/runtime/onchain.py:194-261`):

```python
from helios_allocator.runtime import AllocatorOnChain

oc = AllocatorOnChain(
    rpc_url=os.environ["KITE_RPC_URL"],
    operator_pk=os.environ["ALLOCATOR_OPERATOR_PK"],
    allocator_vault_address=os.environ["ALLOCATOR_VAULT"],
    allocator_registry_address=os.environ["ALLOCATOR_REGISTRY"],
    chain_id=2368,
)
oc.register_allocator(
    name="Acme Allocator",
    ranking_function_hash=keccak(b"acme.v1"),
    supported_classes=[ClassIds.MOMENTUM_V1, ClassIds.MEAN_REVERSION_V1],
    fee_rate_bps=500,
    stake_amount=10_000_000_000,  # 10,000 USDC, 6 decimals
)
```

Reserved-name enforcement is on-chain: the constructor pre-seeds
`"helios sentinel"` and `"helios helix"`
(`AllocatorRegistry.sol:63-64`); any registration with a
case-insensitive `Helios *` match reverts `ReservedName()`.

### Stake management

The CLI ships four `stake` subcommands
(`packages/helios-cli/src/helios_cli/allocator.py:501-582`):

```bash
helios-allocator stake top-up \
    --allocator-id 0xYourAllocatorVault \
    --amount 5000000000 \
    --rpc-url https://rpc-testnet.gokite.ai \
    --operator-pk $ALLOCATOR_OPERATOR_PK

helios-allocator stake initiate-withdrawal --allocator-id 0x... --amount 2000000000
# wait for the cooldown window (see Helios.md §6.6 / AllocatorRegistry.stakeCooldown)
helios-allocator stake withdraw      --allocator-id 0x...
helios-allocator stake balance       --allocator-id 0x...
```

`top-up` issues two transactions: `USDC.approve(AllocatorRegistry,
amount)` and `AllocatorRegistry.topUpStake(allocatorId, amount)`. The
CLI reads the registry and USDC addresses from
`contracts/deployments/<chain>.json` automatically — pass `--registry
0x...` to override.

> **Note:** the AllocatorRegistry has **no `setSigner` function**.
> Strategy operator signing keys (`ReputationAnchor.setSigner` etc.)
> are an oracle/anchor convention; the allocator EOA stored in
> `AllocatorEntry.operator` is the only address with stake-management
> rights and is set immutably at `registerAllocator` time
> (`AllocatorRegistry.sol:91`). If you want a hot-key /
> cold-key split, deploy a multisig or smart-account wallet and pass
> *that* as the operator at registration. Key rotation today requires
> a fresh registration under a new name (or a v2 registry redeploy).

---

## 5. Reputation mechanics

The full formula lives in `docs/reputation-math.md` ("Allocator
reputation v1"). The four allocator-specific signals, in dominance
order:

| Component | Weight | What moves it |
|---|---|---|
| **PnLScore** | 0.55 | `Σ user net P&L above HWM / Σ AUM`, clipped to [-1, +1]. Above-HWM netting prevents a drawdown-recovered position from double-paying; AUM netting prevents a small allocator with one lucky win from outranking a large allocator with a steady book. |
| **DrawdownDiscipline** | 0.20 | `breach_response_count / breach_total_count` where "responded" means the allocator defunded the affected user within `DRAWDOWN_RESPONSE_SEC = 60`. Zero-breach windows return 1.0. |
| **RetentionScore** | 0.15 | Users who keep capital with you across the rolling 30-day window. Long-run economics; users vote with their feet. |
| **StakeScore** | 0.10 | `log(1 + s/1000) / log(1 + max_s_in_class/1000)`. Same curve as strategies (`Helios.md §8.2`). Smallest weight on purpose — stake is barrier-to-entry, not skill. |

Cold-start floor: an allocator with **zero users at both ends of the
retention window AND zero breaches in the window** collapses to
`w_stake · StakeScore`. Once users delegate or a breach occurs, the
full formula takes over and the score is non-decreasing in
expectation against the cold-start floor
(`docs/reputation-math.md`, "Cold start — zero users + zero breaches").

What this means for you operationally:

- **Defund discipline is the second-most-valuable signal you have.**
  A 60s-cadence drawdown loop (the SDK default) is necessary, not
  sufficient — you also need to make sure your `tick_once` actually
  hits chain calls when a breach is observed. The SDK's
  `_enforce_drawdown` already wraps this in
  `onchain.defund_async(...)` so your latency is dominated by RPC,
  not Python.
- **Decision frequency vs noise is a tradeoff.** Tightening
  `rebalance_cadence_sec` below the user's mandate is a footgun:
  PnLScore is netted by AUM and drawdowns from churn show up the same
  as drawdowns from bad picks. The user owns the cadence; respect it.
- **Capital efficiency** is implicit in PnLScore — leaving capital
  idle (or over-allocating to one strategy and hitting
  `max_per_strategy_bps`) lowers the numerator without changing the
  denominator. The SDK's `score_weighted_allocation` is the cheapest
  path to "deploy what you can without breaching caps."

Reputation deltas are signed off-chain by the registered reputation
signer and posted to `ReputationAnchor.postReputationUpdate(...)` with
`actor_type = ALLOCATOR`. The on-chain `AllocatorEntry.currentReputation`
field updates atomically (`AllocatorRegistry.sol:174-183`).

> **Note:** the V1 `ReputationAnchor` is the source of truth for the
> allocator score on the AR-v1 registry; the WS11 v1→v2 cutover moved
> the registry binding to `ReputationAnchorV2Bis` on SR-v3 + AR-v2.

---

## 6. Reference implementations

### `services/sentinel/` — minimal viable allocator

Sentinel is the canonical "simplest possible" allocator and the
baseline competing allocators are expected to beat
(`Helios.md §11.2`). Its rank product is exactly `ReputationScore ×
CapacityFactor × FeeFactor × ClassFitFactor` — no correlation
awareness, no regime detection, no ML
(`services/sentinel/src/sentinel/allocator.py:127-133`). It splits
each user's capital into a main pool (rank-product, score-weighted)
and a `bootstrap_share_bps` cold-start pool that funds strategies
under `min_attested_trades` with stake-weighted shares
(`§8.7`, `services/sentinel/src/sentinel/allocator.py:46-71`). Read
this first — your allocator will run on the same
`AllocatorRuntime` plumbing.

### `services/helix/` — correlation-aware reference

Helix-lite v1 swaps Sentinel's binary `FeeFactor` for the SDK's
`helix_fee_factor` — a continuous penalty in `[0, 1]` over the
user's fee headroom, regime-pinned to `NORMAL`
(`Helios.md §11.4`, `services/helix/src/helix/allocator.py:74-80`).
Two strategies that both clear `max_fee_rate_bps` are no longer
equally preferred; the cheaper one scores higher proportionally.
Helix's load-bearing purpose beyond divergence-from-Sentinel is to
prove the AllocatorSDK is real — it was built ground-up on the SDK in
under a week (`Helios.md §11.4`). The SDK already ships the
correlation-aware `helix_greedy_pick`,
`pairwise_correlation_from_goldsky`, and `btc_realized_vol_30d`
hooks for third parties and Helix-v2; v1 Helix does not wire them.

Both are reference brands locked to the Helios multi-sig in
`AllocatorRegistry`. Third-party allocators register under any
non-reserved name and compete on the same `/allocators` directory
in the dashboard.

---

## 7. Operating an allocator

### VPS deployment

`helios-allocator deploy` builds a Docker image from your scaffold
and ships it over SSH to a VPS
(`packages/helios-cli/src/helios_cli/allocator.py:588-630`):

```bash
helios-allocator deploy \
    --project ./acme-allocator \
    --vps helios@vps.example \
    --image-tag acme-allocator:latest
```

The container runs with `--restart unless-stopped` and reads its
environment from `~/.helios/allocator.env` on the VPS. The deploy
flow validates the SSH target with a leading-dash check
(`_validate_ssh_target`, `:633`) and uses `--` after `scp`/`ssh` to
neutralize OpenSSH option-injection.

For the Helios team's own VPS (`helios@38.49.216.27`, see
`MEMORY.md` → "Helios VPS"), `pm2 start
deploy/ecosystem.config.cjs` boots Sentinel + Helix together with
the rest of the stack. You don't need PM2 for a third-party
allocator unless you're running multiple processes.

### Key custody

The allocator EOA is set at registration time and immutable. Three
practical postures, in order of preference:

1. **Smart-account / multisig as operator.** Register with a
   multisig or 4337 smart-account address as `operatorVault`
   `msg.sender`; rotate signing keys inside the wallet without
   touching `AllocatorRegistry`. Compromise of one key is bounded by
   the wallet's policy, not the meta-strategy alone.
2. **Hot EOA + cold stake operator.** Use one funded hot key for
   `allocateToStrategy` / `defundStrategy` / `rebalance` /
   `settleStrategyFee` (the four operator calls in
   `AllocatorVault`), and a separate cold key for stake top-ups —
   `topUpStake` accepts any caller, only stake withdrawal is gated
   on the registered operator
   (`AllocatorRegistry.sol:120-129`).
3. **Single hot EOA.** Acceptable on testnet during bring-up; do not
   use it for mainnet capital.

The Passport stack (`KITE_PASSPORT_SESSION_ID` /
`KITE_PASSPORT_NETWORK`) is **user-side**, not allocator-side —
allocators sign with raw EOAs because the operator vault needs
unattended tx submission. Don't add a Passport session to your
allocator's `.env`.

### Rate limits

The Helios reference VPS fronts allocator endpoints with nginx and
three `limit_req_zone`s
(`deploy/nginx/helios.conf:34-36`):

| Zone | Rate | Burst |
|---|---|---|
| `helios_read` | 100 r/m | 20 |
| `helios_write` | 10 r/m | 2-3 |
| `helios_prover` | 5 r/m | 1 |

Sentinel's `/v1/onboard` and dashboard write endpoints sit behind
`helios_write`; reads (`/v1/users`, `/v1/allocations`,
`/v1/strategies`) sit behind `helios_read`
(`deploy/nginx/helios.conf:124-159`). Third-party allocators running
on their own VPS should reuse the same shape — your write
surface is unbounded by construction (any user can call `/v1/onboard`)
and a 429-friendly client beats a flooded loop.

Full table (zone, burst, method splitting, restart-runbook
references) lives in [`deploy/README.md`
"Rate limits"](../deploy/README.md). Tripping a limit returns
**HTTP 429** — back off rather than retrying immediately.

---

## 8. Testing your allocator

### Unit tests

`pytest` against the SDK's runtime is the fast path:

```bash
cd acme-allocator
pytest -q
```

The SDK gives you four hooks for tests that don't need a chain:

- `AllocatorLoop.seed_candidates(...)` — inject `StrategyCandidate`
  rows without HTTP
  (`packages/allocator-sdk/src/helios_allocator/runtime/loop.py:420`).
- `AllocatorLoop.seed_directory(...)` — same for directory rows
  the dashboard reads (`:425`).
- `AllocatorOnChain` stub mode — instantiate with empty
  `allocator_vault_address`; every chain call is a no-op that records
  what it *would have* submitted in `pending`
  (`runtime/onchain.py:65-72`).
- `AllocatorLoop.tick_once(now=...)` — drives the full six-step cycle
  with deterministic timestamps. The Phase 1 acceptance scenario
  (allocate → drawdown breach → reallocate) lives in
  `services/sentinel/tests/test_loop.py::test_full_scenario_allocate_drawdown_reallocate`
  — copy that pattern.

### Multi-user simulation

`helios-allocator simulate` sweeps N synthetic users through your
ranker
(`packages/helios-cli/src/helios_cli/allocator.py:265-303`):

```bash
helios-allocator simulate \
    --allocator src/acme_allocator/allocator.py:AcmeAllocator \
    --users 100 \
    --seed 42
```

Output is a "times picked" table per strategy plus aggregate
capital deployed. Useful for tuning fee/correlation thresholds
against typical user populations before live deploy.

### Backtest

Backtests run against historical strategy NAV traces
(`packages/helios-cli/src/helios_cli/allocator.py:196-229`):

```bash
helios-allocator backtest \
    --allocator src/acme_allocator/allocator.py:AcmeAllocator \
    --capital 50000 \
    --period 90d \
    --output docs/backtests/acme_allocator_90d.md
```

Periods supported: `7d`, `30d`, `90d`, `180d`, `1y`. The runner
prints a Rich table summarizing total return, Sharpe, max drawdown,
and allocator fees paid; pass `--output` to also write a markdown
report.

> **Note:** without `--fixture path/to/series.json`, the backtest
> requires a live Goldsky endpoint. The "live" path requires a
> running subgraph and is exercised end-to-end in WS7 — until your
> test infra has Goldsky access, pass a JSON fixture of pre-recorded
> `StrategyNavSeries` rows
> (`packages/helios-cli/src/helios_cli/allocator.py:232-244`).

### Scenario / replay mode

The Sentinel service exposes `scenario_mode` in its settings
(`services/sentinel/src/sentinel/service.py:194`). For your own
allocator, reach for `seed_candidates` + `tick_once` instead — it's
the same machinery without the SCENARIO_MODE switch baggage. The
project memory ("Test against the real product, not seed scripts")
applies: don't lean on scenario mode to mask stack gaps once you're
past local bring-up.

### Live tail

Once deployed, follow the structured event log:

```bash
helios-allocator logs --vps helios@vps.example --lines 500 --follow
```

This is `docker logs --tail=500 -f helios-allocator` over SSH
(`packages/helios-cli/src/helios_cli/allocator.py:655-675`); the
Sentinel/Helix reference services emit `structlog` JSON, one line per
on-chain action.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `helios-allocator init` rejects `--name` | Name matches reserved `Helios *` namespace, or snake-case form isn't a Python identifier. | Pick a non-`Helios *` name with ASCII letters, digits, and spaces. |
| `registerAllocator` reverts `ReservedName()` | Same root cause as above, on-chain enforcement. | Same fix. |
| `topUpStake` reverts at `ERC20InsufficientAllowance` | Approve race or non-standard USDC. | Set `--registry 0x...` explicitly to the deployed `AllocatorRegistry` and confirm `stakeToken` is the USDC your script approved. |
| `completeStakeWithdrawal` reverts `StakeCooldownActive()` | Cooldown window not elapsed. | Wait `AllocatorRegistry.stakeCooldown` from `initiateStakeWithdrawal`; `helios-allocator stake balance` prints the unlock timestamp. |
| Loop never fires `defundStrategy` even after a drawdown | `drawdown_threshold_bps` is 0 in the user's meta-strategy, or the strategy's `nav_samples` ring isn't being populated. | Check `UserVault` for the user's `MetaStrategy.drawdownThresholdBps` and confirm `chain_watch` is mirroring `reportNAV` events into `AllocationState.nav_usd`. |
| Scaffold's `python -m acme_allocator` exits with `LoopConfig` TypeError | Scaffold drift from current SDK signature (see §1 Note). | Replace the scaffolded `__main__.py` body with the wiring in `services/sentinel/src/sentinel/service.py:96-122`. |

---

## Reference implementations

The two reference allocators in `services/` are
production-grade — full FastAPI services, `AllocatorRuntime` boot,
chain-mirror telemetry, x402 / WebSocket dashboard surfaces. Read
them when you're ready to graduate from a single-file allocator:

- `services/sentinel/` — Sentinel-style `ReputationScore × Capacity ×
  FeeFactor × ClassFit` baseline + cold-start bootstrap pool
- `services/helix/` — continuous-fee-fit divergence over
  `score_weighted_allocation` (Helix-lite v1)

Both register against the same `AllocatorRegistry`, hit the same
`AllocatorVault`, and report into the same `ReputationAnchor`. The
only thing that distinguishes them on the dashboard is their
`rankingFunctionHash` and their realized user outcomes — which is the
whole point.
