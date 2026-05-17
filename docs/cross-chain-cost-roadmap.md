# Cross-chain cost roadmap

Cost-reduction levers for Helios's §12.1 cross-chain capital routing.
Tier 1 + Tier 2 shipped already; Tier 3 + Tier 4 are tracked here 

## v1 status — cross-chain CAPITAL flow is OFF (decision, 2026-05-17)

**v1 ships with live cross-chain capital movement disabled.** After
Tier 1 + Tier 2, a single `OFT.send` still costs ~1.0–1.2 KITE in
LayerZero V2 DVN + executor fees — a *fixed* cost independent of payload
that the levers below can only amortize, never remove (see the fee
breakdown: the DVN + executor floor is structural). At the testnet
rebalance cadence this burns KITE faster than the capability is worth
on a demo: ~35 KITE was spent before this call was made. Per-rebalance
bridging is **not practical** under LZ V2 testnet fee economics, so it
is a deliberate v1 cut rather than a bug to chase.

What this means concretely:

- The Sentinel loop never attempts `allocateToRemoteStrategy` /
  `allocateToRemoteStrategyBatch`. Every remote-chain op deterministically
  becomes a zero-cost `CROSS_CHAIN_ALLOCATION_DEFERRED` event — the
  dashboard still shows cross-chain *intent*, no KITE is spent.
- Gated by the master kill-switch `cross_chain_capital_enabled`
  (`LoopConfig`, default `False`) wired from
  `SENTINEL_CROSS_CHAIN_CAPITAL_ENABLED` (default `false`). It short-
  circuits the live send even when the OFT adapter is fully wired, so
  the off-state is fail-safe, not "blank env var by accident".
- Base/Arb strategies still appear in the directory + candidate set
  (`/strategies`), and the Tier 1/Tier 2 levers below remain in the
  code — re-enabling is a single flag flip for v2 work / measurement.
- **Cross-chain *reputation* propagation is unaffected and remains
  live** — it is core to the Helios narrative. It is a *separate,
  KITE-free* path, for a structural reason: rep messages
  (`HeliosOApp.sendReputationUpdate` / batched `flushAttestations`)
  only ever **originate on Base/Arb** —
  `StrategyVault._forwardAttestationIfRemote` is a hard no-op when
  `block.chainid == Kite`. Kite is purely the receiver
  (`_lzReceive` → `postCrossChainUpdate`); receiving costs the operator
  nothing. So the LZ `nativeFee` is paid in **Base/Arb Sepolia testnet
  ETH** (free from faucets), not the scarce KITE that the capital
  `OFT.send` burned. Live quotes (Base→Kite and Arb→Kite, single
  update, 200k-gas lzReceive, measured 2026-05-17): **~9.9 × 10⁻⁵ ETH
  per message** (`98_985_491_284_465` wei Base / `98_985_486_885_430`
  wei Arb). Note the asymmetry: the same DVN+executor+protocol fee
  *components* are priced ~4 orders of magnitude apart between the two
  endpoints' configs — Kite's endpoint quoted ~1 KITE for the capital
  send; Base/Arb→Kite quotes ~0.0001 (free) ETH. Reputation also
  batches N attestations into one message and fires on a slow cadence
  (rep changes slowly + skip-unchanged gating), so even that is
  amortized. Net: negligible in both native amount and token scarcity.
  (Quotes are current testnet values; LZ testnet DVN/executor pricing
  and source gas price can drift.)

### v2 — making Helios useful cross-chain (the reframe, not just "turn it back on")

The v1 lesson is that *per-rebalance capital bridging* is the wrong
unit of work for LZ V2's fixed-fee shape. v2 should make the
cross-chain story valuable without paying a ~1 KITE floor per
allocation delta. Candidate directions, to be designed in v2:

- **Settlement-only bridging (Tier 4 evolved).** Capital stays on its
  home chain; only net realized PnL / reputation settles cross-chain on
  a slow cadence. Per-allocation bridging disappears entirely.
- **Multi-user / multi-strategy aggregation per (dst chain, epoch).**
  One hop per chain per settlement window amortizes the fixed fee
  across every user and strategy (see Tier 4 below — promoted from
  "deferred lever" to the v2 design centre).
- **Intent-based / off-chain-matched routing.** Express the
  cross-chain target as a signed intent; bridge only when an aggregated
  batch clears a fee-justifying size threshold.

These are tracked, not committed, and explicitly out of v1 scope. Tier 3
and Tier 4 below remain the cost-side groundwork they build on.

## Cost shape today (Kite testnet, post-Tier 1+2)

LayerZero V2 charges a near-flat fee per `OFT.send` regardless of payload
size. Empirical measurements:

| Lever | Effect | Per-hop cost (Kite testnet) |
|---|---|---|
| Baseline (CXR-0c, pre-Tier 1+2) | per-strategy `OFT.send` | ~1.0 KITE/hop × N strategies |
| Tier 1: threshold (`min_cross_chain_alloc_usd_wei`) | drops dust ops | same per-hop, but fewer hops |
| Tier 1: flush cadence (`cross_chain_flush_cadence_sec`) | spaces re-fires within window | same per-hop, but fewer hops |
| Tier 2: batched-compose (`allocateToRemoteStrategyBatch`) | 1 hop carries N same-destination strategies | ~1.0 KITE/hop ÷ N |

Cold-start broadcast at the §12.1 demo scale (1 user, mom.base + mr.base +
yr.arb): **3.2 KITE → ~2.2 KITE** with Tier 2 (mom.base + mr.base collapse
to one Base hop; yr.arb stays its own hop because different dst chain).
Steady-state with Tier 1 gates: drops below 1 KITE/hour on a quiet
rebalance pattern.

### Fee component breakdown

For one `OFT.send` to Arb-Sepolia at 200k+200k lzReceive+lzCompose gas
options (commit `95286e6`):

| Component | Share | Source of cost | Adjustable? |
|---|---|---|---|
| DVN fee | ~0.8 KITE | LZ Labs DVN signature per message | Yes — drop to 1-of-1 (Tier-7) but severe security tradeoff |
| Executor base fee | ~0.15 KITE | Per-message floor | No (Kite endpoint default) |
| Executor gas component | ~0.05 KITE | extraOptions × destination gas price | Already trimmed; further reduces risks OOG on destination |
| Protocol fee | negligible | LZ V2 message-relay overhead | No |

Halving compose gas (500k → 200k) dropped fee only ~10%. The DVN +
executor floor dominates.

## Levers shipped (Tier 1 + Tier 2)



- **Tier 1** — config-only gates in `loop._defer_remote_ops`:
  - `LoopConfig.min_cross_chain_alloc_usd_wei` (default 10e18 = $10) —
    skip sub-threshold ops silently; let the delta accumulate.
  - `LoopConfig.cross_chain_flush_cadence_sec` (default 300s) — bound
    the per-(user, strategyId) submit rate so 60s ticks don't burn one
    LZ V2 fee each.
  - Pass-through in `services/sentinel/service.py` settings +
    `deploy/env.prod.example` env vars.
- **Tier 2** — multi-strategy batching on same destination chain:
  - `AllocatorVault.allocateToRemoteStrategyBatch(RemoteBatchParams)` —
    packs N entries into one `OFT.send` with sum-of-amounts as the OFT
    `amountLD` and a batched composeMsg.
  - `HeliosBridgeReceiver` action `ACTION_ALLOCATE_BATCH = 2` decodes
    arrays and loops `_allocateOne` per index; partial-failure recovery
    via the existing `recoverable[user]` pattern (one bad entry
    doesn't roll back the batch).
  - allocator-sdk `allocate_to_remote_batch` builder + `loop._flush_cross_chain_group`
    groups by `dst_eid` and picks single-call vs batched dispatch.
  - Subgraph `CrossChainAllocation` entity tracks per-strategy events;
    consumers group by `txHash` for batch cardinality.

## Roadmap (Tier 3 + Tier 4 — deferred past v1)



### Tier 3 — Drop the lzCompose hop (architectural)

Today an `OFT.send` with composeMsg triggers two destination-chain
executor invocations: `_lzReceive` on the OFT adapter (releases USDC)
+ `lzCompose` on `HeliosBridgeReceiver` (dispatches to StrategyVault).
Two executor fees per cross-chain hop, ~50% of which is fixed-cost.

**Design sketch.** Fold `HeliosBridgeReceiver`'s dispatch into the OFT
adapter's `_credit` hook. The OFT message payload carries the action +
composeMsg inline; on token release, `_credit` decodes and dispatches
to the local StrategyVault directly. No separate `lzCompose` call.

- Refactor `MUsdcOFTAdapter` to inherit `OFTAdapter` and override
  `_credit(address to, uint256 amount, uint32 srcEid)`.
- Embed the action+payload in the standard OFT message payload (LZ V2
  OFT supports a `composeMsg` slot — verify shape in the adapter ABI).
- Sender-side `extraOptions` drops the `lzCompose` TLV; only `lzReceive`
  gas budget remains.

**Expected savings.** One executor fee removed per hop: ~30–40% per
cross-chain message. Stackable with Tier 2 — combined ~55–60% reduction
on a 3-candidate cold-start.

**Risks.**
- Changes the LZ invocation pattern — needs careful test coverage for
  both allocate + defund directions.
- Mainnet OFT adapter contracts are immutable. Going live with Tier 3
  on mainnet means a fresh adapter deploy (CXR-0a-v2) + peer rewire.
- The current `recoverable[user]` fallback assumes a separate compose
  step; folding into `_credit` means revert semantics change. New tests
  needed to confirm partial-failure recovery still works.

**Trigger conditions.** Worth pursuing when (a) mainnet LZ V2 economics
make the second executor fee a real cost line item, or (b) testnet KITE
faucet supply is consistently rate-limiting demo broadcasts.

### Tier 4 — Multi-user aggregation per (strategy, dst chain)

Today `allocateToRemoteStrategyBatch` aggregates across strategies for
**one** user. At multi-tenant scale (N users each holding a slice of
mom.base), N submits fire — even though all the capital is going to
the same destination vault.

**Design sketch.** AllocatorVault queues pending allocates per (dstEid,
strategyId), flushes via a keeper every `multi_user_flush_sec` with a
single `OFT.send` carrying `(user[], amount[])`.

- New action constant `ACTION_ALLOCATE_MULTIUSER = 3`.
- `StrategyVault.onCrossChainAllocate(address[] users, uint256[] amounts)` —
  new signature that updates per-user accounting in a loop.
- Sender-side: `AllocatorVault.flushMultiUserBatch(strategyId, dstEid, users[], amounts[])`
  reads the queue and emits one `OFT.send`.
- Keeper sweeps queues on a configurable cadence; alternatively triggered
  by a queue-depth threshold (e.g., 5 users or $10k pending).

**Expected savings.** Linear with concurrent users on a given strategy
+ destination chain. For mom.base with 100 active users, ~99% reduction
vs per-user sends.

**Risks.**
- Per-user state needs deterministic batch boundaries: a user can't
  appear twice in one batch (would double-credit the strategy).
- Per-user revert recovery: if one user's allocation reverts in the
  destination `onCrossChainAllocate` loop, the rest must still settle.
  Mirror Tier 2's `recoverable[user]` pattern per-index.
- Latency tradeoff: users wait up to `multi_user_flush_sec` for their
  capital to bridge. Acceptable for routine rebalances; less so for
  drawdown-driven moves. Drawdown-triggered ops should fire immediately
  via the single-call path; only steady-state rebalances queue.
- Subgraph `CrossChainAllocation` entity adds `userIndex` + `batchUsers`
  fields to track per-batch user cardinality.

**Trigger conditions.** Multi-tenant production scale (≥10 concurrent
users on any single strategy). Pre-v1 there's exactly one demo user; no
amortization opportunity exists yet.

## Verification — measuring the Tier 1+2 savings

After the AllocatorVault batch impl lands on Kite:

```bash
# Same-day broadcast, Tier 2 active
python3 /tmp/probe_quote.py
# Expect: 1 send to dstEid 40245 with composeMsg carrying 2 strategies
# Native fee: ~0.995 KITE for Base (vs 2 × 0.995 KITE pre-Tier-2)

# Subgraph query — group cross-chain allocations by txHash to compute
# batch size empirically. helios/v0.9.0+
query BatchSizeByTx {
  crossChainAllocations(orderBy: sentAt, orderDirection: desc, first: 50) {
    id
    txHash
    amount
    strategyId
    dstEid
    sentAt
  }
}
# Group rows by txHash client-side; batch size = count of siblings.
```

Sentinel-side log signals (post-Tier 1+2 deploy):
- `allocator.allocation.cross_chain.threshold_skip` — Tier 1 threshold
  dropped a sub-$10 op.
- `allocator.allocation.cross_chain.flush_window` — Tier 1 flush cadence
  suppressed a re-fire within the cooldown.
- `allocator.allocation.cross_chain.batch_submitted` — Tier 2 grouped
  N strategies into one send (look for `batch_size > 1`).
- `allocator.allocation.cross_chain.submitted` — per-strategy event
  (logged on both single + batch paths so dashboard cardinality stays
  per-strategy).
