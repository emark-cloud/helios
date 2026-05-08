# Helios — Circuit specifications

Forensic spec for the three Groth16 circuits shipped in v1. Authoritative
source is `Helios.md §9`; the .circom files in `circuits/` are the
implementation. When this file and the spec disagree, the spec wins —
but where the implementation enforces invariants the spec does not
mention, those are flagged as **(implementation-only)** and the
.circom file is the ground truth for what the circuit actually does.

Last reviewed: **2026-05-08** against the live `circuits/build/<class>/<class>.r1cs`
artifacts and the verifier-adapter rotation in
`contracts/deployments/kite-testnet.json` (TAV class map rotated
2026-05-07 — see `CLAUDE.md` "Phase-3 deploy state").

Conventions:

- Field types are quoted from the .circom range checks — a "uint64"
  here means the circuit calls `Num2Bits(64)` on that signal, not that
  Solidity uses `uint64`.
- Public-input order matches `circuits/<class>.circom`'s
  `component main { public [...] }` and the `StrategyVault.PI_*`
  constants in `contracts/src/StrategyVault.sol:60` (directional
  classes share a 14-PI layout; `yield_rotation_v1` uses its own 13-PI
  layout — no shared `PI_*` block).
- Constraint counts are read directly from `snarkjs r1cs info` against
  the `.r1cs` artifacts produced by `circuits/Makefile`'s default
  PTAU 16 build.

---

## 1. `momentum_v1`

**Class id (Poseidon):**
`0x2a9aa442064b635baec37a7a259282faa5563a653a8325378d5676c6f04bc9dd`
(`Poseidon([int.from_bytes(b"momentum_v1", "big")])`, pinned in
`contracts/src/ClassIds.sol:28`).

**Source:** `circuits/momentum_v1.circom`. Universe size hard-coded to
8 in the `component main` instantiation (line 307).

### 1.1 Public inputs (14 signals)

The order below is the order in `component main { public [...] }`.
The `StrategyVault.PI_*` constants and the
`MomentumV1VerifierAdapter._PUBLIC_INPUT_COUNT = 14`
(`contracts/src/verifiers/MomentumV1VerifierAdapter.sol:23`) bind to
this layout — reordering breaks both call sites silently.

| # | Signal | Field type | Binds |
|---|---|---|---|
| 0 | `trade_hash` | BN254 scalar (Poseidon output) | Poseidon(10) over the canonical public-fields tuple — see Constraint 7 below. Cross-vault replay protection + cheap dedup key for `_seenTradeHash`. |
| 1 | `declared_class` | BN254 scalar | Poseidon class id — keccak digests overflow BN254 and would fail the verifier's `checkField`. On-chain checked against `ClassIds.MOMENTUM_V1`. |
| 2 | `strategy_vault` | uint160 (address) | The calling vault; the on-chain side asserts `address(this) == publicInputs[PI_STRATEGY_VAULT]` so the proof cannot replay across sibling vaults. |
| 3 | `params_hash` | BN254 scalar | `Poseidon(max_position_size, max_slippage_bps, signal_threshold, stop_loss_price)`. On-chain checked against `_activeParamsHash()` (registry-committed via `commitInitialParamsHash` / `rotateParams`). |
| 4 | `allocator_address` | uint160 | Whichever allocator submitted the trade. Bound into `trade_hash`. |
| 5 | `asset_in_idx` | bounded by `Num2Bits(8)` and strict `< UNIVERSE_SIZE` | Manifest-resolved index; manifest enforces `UNIVERSE_SIZE == 8` at registration. |
| 6 | `asset_out_idx` | same bound | as above. |
| 7 | `amount_in` | `Num2Bits(128)` | Token amount being spent. |
| 8 | `min_amount_out` | `Num2Bits(128)` | Slippage bound. |
| 9 | `trade_direction` | derived: `is_long_entry + 2·is_short_entry` | `0 = exit, 1 = long entry, 2 = short entry`. |
| 10 | `nonce` | unconstrained scalar | Cross-vault dedup. |
| 11 | `block_window_start` | unconstrained; `windowDelta` is `Num2Bits` via `LessEqThan(64)` | Lower bound of the block-execution window. |
| 12 | `block_window_end` | as above | Upper bound. |
| 13 | `oracle_root` | BN254 scalar (Poseidon output) | Final hash of the chained Poseidon over the 16 private price observations; on-chain checked against `IOracleAnchor.freshness(root)` with a 180-second cap (see `_MAX_ORACLE_STALENESS_SEC` in `StrategyVault.sol:200`). |

### 1.2 Private inputs (witness)

| Signal | Field type | Notes |
|---|---|---|
| `max_position_size` | `Num2Bits(128)` | Operator-declared cap. Pinned to `params_hash`. |
| `max_slippage_bps` | `Num2Bits(14)` and `LessEqThan(14)` against `10000` | Pinned to `params_hash`. The 10 000-bps ceiling is required so `(10000 - max_slippage_bps)` cannot wrap the field. |
| `signal_threshold` | `Num2Bits(32)` | bps. Pinned to `params_hash`. |
| `stop_loss_price` | `Num2Bits(64)` | Pinned to `params_hash`. |
| `price_observations[16]` | each `Num2Bits(64)` | The 16 minute-bars whose chained Poseidon must equal `oracle_root`. |
| `is_long_entry`, `is_short_entry`, `is_exit` | boolean (one-hot) | One-hot direction selector; `is_long_entry + is_short_entry + is_exit === 1`. |
| `is_signal_flip`, `is_stop_loss` | boolean (one-hot when `is_exit`) | Exit-reason selector; `is_exit === is_signal_flip + is_stop_loss`. |
| `was_long` | boolean | **(implementation-only — closes Phase-3 review HIGH #11.)** Side of the position being unwound on a signal-flip exit. `1 = was long, 0 = was short`. Unconstrained when `is_signal_flip = 0`. |

### 1.3 Invariants enforced

Numbered to match the `Constraint N` headers in `momentum_v1.circom`.

- **A. `params_hash` binding** — `Poseidon(max_position_size, max_slippage_bps, signal_threshold, stop_loss_price) === params_hash` (lines 81–86). Combined with the on-chain `_activeParamsHash()` check, this pins the operator's declared parameters to the registry.
- **A.1. Slippage range** — `max_slippage_bps ≤ 10000` (lines 90–95). Prevents the `(10000 - max_slippage_bps)` term in Constraint 2 from wrapping.
- **A.2. Price-observation width** — every `price_observations[i]` ≤ 2⁶⁴ (lines 105–109). Threshold ≤ 2³², stop-loss ≤ 2⁶⁴ (lines 110–113). Without these the squared / scaled deltas in Constraint 4 could wrap mod the field.
- **B. Asset-index range** — `asset_in_idx, asset_out_idx ∈ [0, UNIVERSE_SIZE)` (lines 117–128).
- **B.1. No self-swap** — `asset_in_idx ≠ asset_out_idx` **(implementation-only — Phase-3 review HIGH #12.)** `IsEqual(...).out === 0` at lines 135–138. Closes a no-op-swap bypass that the spec did not cover.
- **B.2. Amount widths** — `amount_in, min_amount_out, max_position_size` all `Num2Bits(128)` (lines 147–152). 128 bits keeps `amount_in × (10000 - max_slippage_bps)` well below BN254 so a near-field witness cannot wrap and still pass `GreaterEqThan(160)`. **(implementation-only — Phase-3 review HIGH #13.)**
- **1. Size cap** — `amount_in ≤ max_position_size` via `LessEqThan(128)` (lines 155–158).
- **2. Slippage bound** — `min_amount_out · 10000 ≥ amount_in · (10000 - max_slippage_bps)` via `GreaterEqThan(160)` (lines 162–169).
- **3. Oracle root** — chained Poseidon: `h[0] = P(obs[0])`, `h[i] = P(h[i-1], obs[i])` for `i ∈ 1..15`, then `h[15] === oracle_root` (lines 175–186).
- **4. Direction-specific signal logic** (lines 188–227):
  - One-hot direction selector and `trade_direction === is_long_entry + 2 · is_short_entry`.
  - On long entry: `(price_last − price_first) · 10000 ≥ signal_threshold · price_first`.
  - On short entry: `(price_first − price_last) · 10000 ≥ signal_threshold · price_first`.
  - Non-active branch is masked by the direction selector so its non-negativity check trivially holds.
  - Non-negativity proven via `Num2Bits(192)` on the masked excess.
- **5. Block window bound** — `block_window_end − block_window_start ≤ 100` via `LessEqThan(64)` (lines 230–235).
- **6. Exit conditions** (lines 237–272):
  - Signal-flip OR stop-loss, never both: `is_exit === is_signal_flip + is_stop_loss`.
  - Signal-flip excess is computed as `was_long ? down_delta : up_delta`, both minus `signal_threshold · price_first`. **(implementation-only — Phase-3 review HIGH #11.)** The spec only described long→down reversals; without `was_long`, a short position could not exit via flip.
  - Stop-loss: `stop_loss_price − price_last ≥ 0`.
- **7. `trade_hash` binding** — `Poseidon(strategy_vault, declared_class, params_hash, allocator_address, asset_in_idx, asset_out_idx, amount_in, min_amount_out, trade_direction, nonce) === trade_hash` (lines 277–288). `strategy_vault` is included so a sibling vault registering the same momentum verifier cannot accept the proof.

### 1.4 Output semantics

No public outputs. The trade's direction, sizing, and asset pair are
all public inputs (slots 5–9). The off-chain consumer reads
`trade_direction` to label the trade as exit / long / short and the
asset indices to resolve to `manifest.assetUniverse` addresses.
Slippage is enforced as a ratio (`min_amount_out / amount_in`); the
realised execution price is whatever the swap router returns.

### 1.5 Constraint count + PTAU sizing

`snarkjs r1cs info circuits/build/momentum_v1/momentum_v1.r1cs`:

```
# of Wires:           7390
# of Constraints:     7396
# of Private Inputs:  26
# of Public Inputs:   14
# of Labels:          18652
```

Per-circuit budget (`circuits/Makefile` `BUDGET_momentum_v1`): **20 000**
non-linear constraints. Current build: **7 396** = 37% of budget. PTAU
16 ceiling is 65 535 constraints — comfortable headroom.
`make check-constraints` fails CI at 90% of budget.

### 1.6 Test coverage

`circuits/test/momentum_v1.test.js` exercises:

- Zero / max / boundary
  - `valid witness generates` — happy-path long entry on a monotonically rising series.
  - `amount_in over cap rejected` — Constraint 1.
  - `asset_in_idx out of range rejected` — `idx == UNIVERSE_SIZE`, Constraint B.
  - `window > 100 blocks rejected` — Constraint 5.
  - `max_slippage_bps over 10000 rejected` — Constraint A.1.
- Hash bindings
  - `trade_hash mismatch rejected` — Constraint 7.
  - `params_hash mismatch rejected` — Constraint A.
  - `oracle root mismatch rejected` — Constraint 3.
- Signal logic
  - `long entry without sufficient momentum rejected` — Constraint 4 long branch.
  - `direction-selector mismatch rejected` — one-hot violation.
- Exit branches
  - `exit (signal flip) accepted on falling prices` and rejected when prices still rising.
  - `exit (stop loss) accepted` and rejected when stop below last price.
  - `exit with neither flip nor stop-loss reason rejected`.
  - `short signal-flip exit accepted on rising prices` (HIGH #11).
  - `signal-flip with wrong was_long rejected` (HIGH #11).
- Self-swap
  - `self-swap rejected` (HIGH #12).
- Zero-amount reject (Constraint 0)
  - `amount_in == 0 rejected` — added 2026-05-08 alongside the new
    `Num2Bits(128)` positivity constraint mirroring `yield_rotation_v1`'s
    `amount_rotating > 0`.
- Bit-width edges
  - `amounts at 2^128 − 1 boundary accepted` — exercises the `Num2Bits(128)`
    width on `amount_in` / `min_amount_out` / `max_position_size` at the
    upper limit.
- Short-entry happy path
  - `valid short entry on falling prices` — Constraint 4 short branch.

---

## 2. `mean_reversion_v1`

**Class id (Poseidon):**
`0x18602f4f74172d545f5258541634e1a125c3a4e1227ee2a4cbee957d3490f1fb`
(`Poseidon([int.from_bytes(b"mean_reversion_v1", "big")])`, pinned in
`contracts/src/ClassIds.sol:32`).

**Source:** `circuits/mean_reversion_v1.circom`. Universe size 8.

### 2.1 Public inputs (14 signals)

Layout is **identical** to `momentum_v1`'s 14-PI tuple, by design — the
`StrategyVault.PI_*` constants and the
`MeanReversionV1VerifierAdapter._PUBLIC_INPUT_COUNT = 14`
(`contracts/src/verifiers/MeanReversionV1VerifierAdapter.sol:21`)
are reused verbatim. See §1.1 for the per-slot table; the only
semantic shift is `signal_threshold`'s interpretation in
`params_hash`.

### 2.2 Private inputs (witness)

Same shape as `momentum_v1` with two semantic differences:

- `signal_threshold` is now `n_sigma_x100` — e.g. `200` ⇒ 2.00σ
  deviation gate. `Num2Bits(32)`.
- No `was_long` slot — the mean-reversion exit logic is symmetric in
  the deviation magnitude, so the long/short asymmetry that drove
  HIGH #11 in `momentum_v1` does not apply here.

### 2.3 Invariants enforced

The non-deviation constraints (params_hash binding, slippage range,
price/threshold/stop widths, asset-index range, no self-swap, amount
widths, size cap, slippage bound, oracle root, block window,
trade_hash) are structurally identical to `momentum_v1`'s — see
§1.3. The .circom line ranges differ; the constraint shapes do not.

The mean-reversion-specific invariants (lines 168–271):

- **Mean-deviation pre-computation.** The circuit avoids stddev by
  working in squared form. Define `sum = Σ price_observations`,
  `dev16[i] = 16·price[i] − sum`, `dev_sq[i] = dev16[i]²`,
  `sum_sq_devs = Σ dev_sq`, `dev_last_sq = dev_sq[15]`,
  `threshold_sq = signal_threshold²`,
  `lhs = 160 000 · dev_last_sq`, `rhs = signal_threshold² · sum_sq_devs`.
- **4a. Entry magnitude.** When `is_long_entry + is_short_entry = 1`,
  the witness must satisfy `lhs ≥ rhs` — i.e. last-bar deviation
  exceeds N-sigma. Excess is `Num2Bits(192)`.
- **4b. Entry sign.**
  - Long entry: `sum − 16·price_last ≥ 0` (price below mean), via
    `Num2Bits(80)` on the masked `is_long_entry · …` signal.
  - Short entry: `16·price_last − sum ≥ 0` (price above mean),
    likewise `Num2Bits(80)`.
  Non-active branch is masked to zero so its non-negativity check is
  trivial.
- **6. Exit conditions.**
  - Signal-flip = mean re-cross = `rhs ≥ lhs` (deviation magnitude has
    fallen below threshold). Excess `Num2Bits(192)` (lines 259–264).
  - Stop-loss: `stop_loss_price − price_observations[15] ≥ 0` (lines
    266–271).
  - `is_exit === is_signal_flip + is_stop_loss`.

The `params_hash` slot for `signal_threshold` is interpreted as
`n_sigma_x100`; field positions in both `params_hash` and `trade_hash`
are unchanged from `momentum_v1` so the on-chain manifest schema is
shared. **(implementation-only.)**

### 2.4 Output semantics

Same as `momentum_v1` — no public outputs; direction and size are
public inputs. Mean-reversion's `signal_threshold` semantically means
`n_sigma_x100` rather than bps return; consumers must read the class
to disambiguate.

### 2.5 Constraint count + PTAU sizing

`snarkjs r1cs info circuits/build/mean_reversion_v1/mean_reversion_v1.r1cs`:

```
# of Wires:           7372
# of Constraints:     7379
# of Private Inputs:  25
# of Public Inputs:   14
```

Budget `BUDGET_mean_reversion_v1`: **20 000**. Current build: **7 379** =
37% of budget. PTAU 16 sufficient.

### 2.6 Test coverage

`circuits/test/mean_reversion_v1.test.js`:

- Entry happy paths
  - `valid long entry on N-sigma down`.
  - `valid short entry on N-sigma up`.
- Exit happy paths
  - `valid exit on mean re-cross`.
  - `valid exit on stop-loss`.
- Range / boundary
  - `amount_in over cap rejected`.
  - `asset_in_idx out of range rejected`.
  - `window > 100 blocks rejected`.
  - `max_slippage_bps over 10000 rejected`.
- Hash bindings
  - `trade_hash mismatch rejected`, `params_hash mismatch rejected`,
    `oracle root mismatch rejected`.
- Signal logic
  - `long entry with insufficient deviation rejected` (Constraint 4a).
  - `long entry with wrong sign rejected` (Constraint 4b long branch).
  - `short entry with wrong sign rejected` (Constraint 4b short branch).
  - `direction-selector mismatch rejected`.
- Exit branches
  - `exit (signal flip) rejected when deviation still beyond threshold`.
  - `exit (stop loss) rejected when stop below last price`.
  - `exit with neither flip nor stop-loss reason rejected`.
- Self-swap
  - `self-swap rejected` (HIGH #12).
- Zero-amount reject (Constraint 0)
  - `amount_in == 0 rejected` — added 2026-05-08 alongside the new
    `Num2Bits(128)` positivity constraint mirroring `yield_rotation_v1`'s
    `amount_rotating > 0`.
- Bit-width edges
  - `amounts at 2^128 − 1 boundary accepted`.
- Exit-reason exclusivity
  - `is_signal_flip + is_stop_loss > 1 rejected` — exercises the
    Constraint 6 sum bound directly rather than relying on the algebra
    + booleanity.

---

## 3. `yield_rotation_v1`

**Class id (Poseidon):**
`0x2e882135c6afc3bda02a9c8a7c6a351198d97599c804a2575a3d616073a87251`
(`Poseidon([int.from_bytes(b"yield_rotation_v1", "big")])`, pinned in
`contracts/src/ClassIds.sol:36`).

**Source:** `circuits/yield_rotation_v1.circom`. Tree depths are
class-level constants: `YIELD_DEPTH = 6` (≤64 markets per oracle
snapshot), `ALLOW_DEPTH = 4` (≤16 allowlisted markets).

### 3.1 Public inputs (13 signals)

This circuit does **not** share the `momentum_v1` PI layout — the
`YieldRotationV1VerifierAdapter._PUBLIC_INPUT_COUNT = 13`
(`contracts/src/verifiers/YieldRotationV1VerifierAdapter.sol:28`) is
its own constant.

| # | Signal | Field type | Binds |
|---|---|---|---|
| 0 | `trade_hash` | BN254 scalar | `Poseidon(12)` over the canonical public-input tuple — see Constraint 9. Cross-vault replay protection. |
| 1 | `declared_class` | BN254 scalar | On-chain checked against `ClassIds.YIELD_ROTATION_V1`. |
| 2 | `strategy_vault` | uint160 | On-chain `address(this)` equality. |
| 3 | `params_hash` | BN254 scalar | `Poseidon(signal_threshold, bridging_cost)` — Constraint 8. On-chain checked against `_activeParamsHash()`. |
| 4 | `markets_allowlist_root` | BN254 scalar | Poseidon Merkle root over allowlisted market ids; on-chain checked against `StrategyRegistry.marketAllowlistRoot(class)`. |
| 5 | `m_from` | scalar | Market id capital is rotating out of. |
| 6 | `m_to` | scalar | Market id capital is rotating into. |
| 7 | `amount_rotating` | `Num2Bits(128)` | Base-asset amount being moved. |
| 8 | `yield_oracle_root` | BN254 scalar | Poseidon Merkle root over `(market_id, apy_bps)` leaves signed by the yield oracle. |
| 9 | `allocator_address` | uint160 | Whichever allocator submitted the trade. |
| 10 | `nonce` | scalar | Cross-vault dedup. |
| 11 | `block_window_end` | unconstrained; `windowDelta` `LessEqThan(64)` | On-chain freshness gate (`block.number ≤ this`). |
| 12 | `block_window_start` | as above | Lower bound. |

### 3.2 Private inputs (witness)

| Signal | Field type | Notes |
|---|---|---|
| `apy_from` | `Num2Bits(16)` | bps. Linked to `m_from` via the yield-oracle Merkle proof. |
| `apy_to` | `Num2Bits(16)` | bps. Linked to `m_to`. |
| `signal_threshold` | `Num2Bits(16)` | bps. Pinned to `params_hash`. |
| `bridging_cost` | `Num2Bits(16)` | bps. Pinned to `params_hash`. |
| `yield_path_indices_from[6]`, `yield_siblings_from[6]` | per-bit boolean indices, scalar siblings | Merkle path for `(m_from, apy_from)` under `yield_oracle_root`. |
| `yield_path_indices_to[6]`, `yield_siblings_to[6]` | as above | Path for `(m_to, apy_to)`. |
| `allow_path_indices_from[4]`, `allow_siblings_from[4]` | as above | Path for `m_from` under `markets_allowlist_root`. |
| `allow_path_indices_to[4]`, `allow_siblings_to[4]` | as above | Path for `m_to`. |

Yield-oracle leaves are `Poseidon(market_id, apy_bps)`; allowlist
leaves are `Poseidon(market_id)`. Tree depths bumping requires
regenerating verifier artifacts (the depth is baked into the circuit).

### 3.3 Invariants enforced

- **1. Yield-oracle inclusion of `(m_from, apy_from)`** — Poseidon
  Merkle proof of `Poseidon(m_from, apy_from)` against `yield_oracle_root`
  (lines 128–139). Each path-indices bit is enforced boolean inside
  `PoseidonMerkleProof` (line 79).
- **2. Yield-oracle inclusion of `(m_to, apy_to)`** — same shape
  (lines 141–152).
- **3. Allowlist inclusion of `m_from`** — Poseidon Merkle proof of
  `Poseidon(m_from)` against `markets_allowlist_root` (lines 154–164).
- **4. Allowlist inclusion of `m_to`** — same (lines 166–176).
- **5. `m_from ≠ m_to`** — `(m_to − m_from)` is forced non-zero by
  asserting `(m_to − m_from) · ((m_to − m_from)⁻¹) === 1`, with the
  inverse supplied as a witness hint via `<--` (lines 178–184).
  Trivially-non-rotating trades are rejected.
- **6. APY differential beats threshold + bridging.**
  `apy_to − apy_from ≥ signal_threshold + bridging_cost`. Range checks
  pin `apy_*`, `signal_threshold`, `bridging_cost` to 16-bit bps so the
  field math cannot wrap (lines 191–198). The differential is shown
  non-negative via `Num2Bits(32)` (line 204).
- **7. `amount_rotating > 0`.** `Num2Bits(128)` on the value plus
  `Num2Bits(128)` on `amount_rotating − 1` (lines 209–214). Reject
  zero-amount rotations (otherwise the proof is decorative).
- **8. `params_hash` binding.** `Poseidon(signal_threshold, bridging_cost) === params_hash`
  (lines 222–225). On-chain check against `_activeParamsHash()` blocks
  per-trade fudging of either threshold without rotating the manifest.
- **8b. Block-window bound.** `block_window_end − block_window_start ≤ 100`
  via `LessEqThan(64)` (lines 234–239). **(implementation-only — review
  followup #5.)** Without `block_window_start` as a PI, any proof minted
  before the registered yield-oracle root could be replayed for the
  entire pre-attestation lifetime; this row was added during the
  Phase-3 redeploy and is not in `Helios.md §9.4`'s 9-PI sketch.
- **9. `trade_hash` binding.** `Poseidon(12)` over
  `(declared_class, strategy_vault, params_hash, markets_allowlist_root,
  m_from, m_to, amount_rotating, yield_oracle_root, allocator_address,
  nonce, block_window_end, block_window_start) === trade_hash`
  (lines 247–260). Each component is also re-checked independently
  on-chain.

### 3.4 Output semantics

No public outputs. The "trade" is a market rotation, not an asset-pair
swap, so the output shape differs from the directional classes:

- `m_from` / `m_to` are lending-market ids (allowlist-resolved on-chain
  to venue addresses). There is no `asset_in_idx` / `asset_out_idx` —
  rotations are within a single base asset.
- `amount_rotating` is the principal being moved (base-asset, e.g.
  USDC). There is no `min_amount_out` — yield-rotation is not a swap;
  slippage is the bridging cost, declared via `bridging_cost` and
  pinned to `params_hash`.
- `trade_direction` is implicit: every yield-rotation trade is a
  rotation, and the constraint set forbids `m_from == m_to`.

### 3.5 Constraint count + PTAU sizing

`snarkjs r1cs info circuits/build/yield_rotation_v1/yield_rotation_v1.r1cs`:

```
# of Wires:           6931
# of Constraints:     6907
# of Private Inputs:  44
# of Public Inputs:   13
# of Labels:          22284
```

Budget `BUDGET_yield_rotation_v1`: **15 000**. Current build: **6 907** =
46% of budget. PTAU 16 sufficient.

### 3.6 Test coverage

`circuits/test/yield_rotation_v1.test.js`:

- Happy path
  - `valid rotation accepted` — 130 bps differential against an 80 + 30 = 110 bps gate.
- Differential gate
  - `differential below threshold rejected` (Constraint 6).
  - `bridging cost erodes differential past threshold` (Constraint 6).
- Allowlist
  - `m_from not in allowlist rejected` (Constraint 3).
  - `m_to not in allowlist rejected` (Constraint 4).
  - `tampered allowlist root rejected` (Constraints 3 + 4 + 9).
- Yield oracle
  - `yield-oracle root mismatch rejected` (Constraints 1 + 2).
  - `apy_from claim diverges from yield-oracle leaf rejected` (Constraint 1).
- Boundary / replay
  - `m_from == m_to rejected` (Constraint 5).
  - `amount_rotating = 0 rejected` (Constraint 7).
  - `trade_hash mismatch rejected` (Constraint 9).
  - `params_hash diverges from (threshold,bridging) rejected` (Constraint 8).
  - `strategy_vault rebinding without trade_hash refresh rejected` (Constraint 9).

**TODO** (gaps):

- No explicit test for the block-window bound (Constraint 8b). The
  carve-out was added in the Phase-3 redeploy and the suite has not
  been backfilled with a `block_window_end - block_window_start > 100`
  reject case.
- No `apy_to` divergence test (mirrors the existing `apy_from` case;
  Constraint 2 is structurally identical to Constraint 1 but
  unexercised against a tampered `apy_to`).
- No tree-depth boundary test — the suite only exercises four active
  markets in a 16-slot allowlist and four snapshots in a 64-slot yield
  tree. Index-edge cases (slot 15 in the allowlist, slot 63 in the
  yield tree) are not covered.
- No `bridging_cost` bit-width-edge test (`Num2Bits(16)` ceiling at
  `2¹⁶ − 1`).

---

## 4. Trusted setup

The v1 hackathon ceremony is a **single-party local Powers of Tau
generation**, executed by the `ptau:` target in `circuits/Makefile`:

1. `snarkjs powersoftau new bn128 16 …` (PTAU 16, supports ≤65 535
   constraints).
2. A single contributor (`helios-local-phase0`) adds entropy from
   `/dev/urandom`.
3. `snarkjs powersoftau prepare phase2` produces the final PTAU.
4. Per-circuit zkey is then `snarkjs groth16 setup` against that PTAU,
   plus a single `helios-local` contribution.

This is documented as suboptimal in `Helios.md §9.5`. A compromised
contributor invalidates Groth16 soundness, so the v1 deployment treats
the setup as a trusted dependency. The production path
(post-hackathon) is either the Hermez-style multi-party ceremony or a
Helios-organised ceremony — see `Helios.md §16` for the timeline.

This carve-out is the **Accepted** half of row 12 in
`docs/threat-model.md` (the "ZK circuit bug" row is otherwise
*Mitigated*; the residual risk on the trusted-setup ceremony is
explicitly Accepted in the §3 "Accepted residual risks" list of that
document). Any change to the ceremony posture must update both
`Helios.md §9.5` and the `docs/threat-model.md` row 12 evidence.

---

## 5. Verifier adapters

The snarkjs-generated verifiers (`contracts/src/verifiers/MomentumV1Verifier.sol`,
`MeanReversionV1Verifier.sol`, `YieldRotationV1Verifier.sol`) expose a
fixed-shape signature:

```solidity
function verifyProof(
    uint256[2] calldata a,
    uint256[2][2] calldata b,
    uint256[2] calldata c,
    uint256[N] calldata publicSignals
) external view returns (bool);
```

where `N` is the public-signal count baked into the zkey. `TradeAttestationVerifier`
(`contracts/src/TradeAttestationVerifier.sol`) — the on-chain dispatch
layer — calls a class-agnostic interface that takes a **dynamic** array:

```solidity
function verifyProof(
    uint256[2] calldata a,
    uint256[2][2] calldata b,
    uint256[2] calldata c,
    uint256[] calldata publicInputs
) external view returns (bool);
```

The mismatch is bridged by per-class adapter contracts in
`contracts/src/verifiers/<Class>VerifierAdapter.sol`. Each adapter:

1. Stores the raw snarkjs verifier as an immutable `inner` reference.
2. Exposes the dynamic-array `IGroth16Verifier.verifyProof` shape.
3. Asserts `publicInputs.length == _PUBLIC_INPUT_COUNT` (14 for
   momentum + mean-reversion, 13 for yield-rotation), reverting with
   `WrongPublicInputCount(got, expected)` on mismatch.
4. Copies the dynamic array into a fixed-size memory buffer of the
   right length and forwards to `inner.verifyProof`.

The TAV class map is rotated by owner via the `propose / commit`
flow on `TradeAttestationVerifier` (see `Helios.md §6.7`):

- `registerVerifier(declaredClass, verifier)` — first-time bind only;
  reverts with `AlreadyRegistered` on a second call. This forecloses
  the "owner-key compromise instantly swaps a verifier" attack.
- `proposeVerifierChange(declaredClass, verifier)` — schedules a
  replacement; emits `VerifierChangeProposed(declaredClass, verifier, readyAt)`.
  `readyAt = block.timestamp + CHANGE_DELAY` and `CHANGE_DELAY` is
  `2 days`.
- `commitVerifierChange(declaredClass)` — applies the proposal once
  the delay has elapsed; emits `VerifierRegistered`.
- `cancelVerifierChange(declaredClass)` — discards a pending proposal.

The pinned class map for the live testnet deployment lives in
`CLAUDE.md` "Key addresses → kite-testnet"; the class-id ↔
adapter-address rotation that landed on 2026-05-07 swapped in the
HIGH #11 / #12 / #13 fixes from `docs/phase-3-review.md`. Bumping any
of the three circuits requires (i) regenerating the snarkjs verifier
via `circuits/Makefile`'s `make <class>` target, (ii) deploying a
fresh adapter pointing at the new raw verifier, (iii) running
`proposeVerifierChange` + waiting `CHANGE_DELAY` + `commitVerifierChange`,
and (iv) re-running `forge test` against `contracts/test/<Class>Verifier.t.sol`
and `contracts/test/TradeAttestationVerifier.t.sol`.
