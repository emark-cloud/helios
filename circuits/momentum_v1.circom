pragma circom 2.1.9;

// Helios — momentum_v1 strategy attestation circuit (v2 layout).
// Helios.md §9.3.
//
// Public-input layout MUST match StrategyVault's PI_* constants in
//   contracts/src/StrategyVault.sol
// AND the MomentumV1VerifierAdapter's _PUBLIC_INPUT_COUNT.
// If you reorder, update both call sites or proofs will silently land on
// the wrong slots.
//
// Proves a single trade satisfies the momentum_v1 class invariants:
//   1. amount_in <= max_position_size
//   2. min_amount_out respects manifest's max slippage
//   3. price_observations Poseidon-chain to a committed oracle root
//   4. direction-specific signal logic (long entry / short entry / exit)
//   5. block_window_end - block_window_start <= 100
//   6. exit conditions: signal-flip OR stop-loss
//   7. params_hash binds (max_position_size, max_slippage_bps,
//        signal_threshold, stop_loss_price) — operator-declared parameters
//        committed on-chain in the strategy manifest. The on-chain code
//        asserts publicInputs[PI_PARAMS_HASH] == manifest.paramsHash, which
//        is what gives the operator-declared bounds their teeth.
//   8. trade_hash binds the public fields (cross-vault replay protection
//        + cheap dedup key for _seenTradeHash).
//   9. asset_in_idx / asset_out_idx are bounded in [0, UNIVERSE_SIZE) —
//        the on-chain manifest resolves indices to addresses, so the
//        circuit only needs to constrain the index range. There is no
//        in-circuit asset_universe witness in this layout.

include "circomlib/circuits/poseidon.circom";
include "circomlib/circuits/comparators.circom";
include "circomlib/circuits/bitify.circom";

// Asset universe size — manifest enforces this on-chain at registration.
template MomentumV1(UNIVERSE_SIZE) {
    // ── Public inputs (order matches StrategyVault.PI_*) ─────────────
    signal input trade_hash;
    signal input declared_class;
    signal input strategy_vault;
    signal input params_hash;
    signal input allocator_address;
    signal input asset_in_idx;
    signal input asset_out_idx;
    signal input amount_in;
    signal input min_amount_out;
    signal input trade_direction;       // 0=exit, 1=long entry, 2=short entry
    signal input nonce;
    signal input block_window_start;
    signal input block_window_end;
    signal input oracle_root;

    // ── Witness (private) ───────────────────────────────────────────
    signal input max_position_size;                 // operator-declared cap
    signal input max_slippage_bps;                  // operator-declared slippage (< 10000)
    signal input signal_threshold;                  // operator-chosen threshold (bps)
    signal input stop_loss_price;                   // operator-declared stop level
    signal input price_observations[16];            // last 16 minute-bars

    // Direction selector witness (one-hot, validated below).
    signal input is_long_entry;
    signal input is_short_entry;
    signal input is_exit;

    // Exit-reason selector witness (one-hot when is_exit, else both 0).
    signal input is_signal_flip;
    signal input is_stop_loss;
    // Side of the position being exited. 1 = the prover is unwinding a
    // long; 0 = unwinding a short. Only consulted when is_signal_flip=1
    // — closes HIGH #11 in `docs/phase-3-review.md` (the previous circuit
    // only modelled long→down reversals, so a short position could not
    // ever exit via flip; completeness bug).
    signal input was_long;

    // ── Constraint A: params_hash binds operator-declared parameters ─
    // On-chain StrategyVault asserts publicInputs[PI_PARAMS_HASH] equals
    // the paramsHash stored in the strategy manifest. Combined with this
    // constraint, the prover can no longer lie about cap / slippage /
    // threshold / stop-loss — they are pinned to whatever the operator
    // committed at registration.
    component paramsPoseidon = Poseidon(4);
    paramsPoseidon.inputs[0] <== max_position_size;
    paramsPoseidon.inputs[1] <== max_slippage_bps;
    paramsPoseidon.inputs[2] <== signal_threshold;
    paramsPoseidon.inputs[3] <== stop_loss_price;
    params_hash === paramsPoseidon.out;

    // max_slippage_bps must be in [0, 10000] so the (10000 - max_slippage_bps)
    // term in the slippage constraint cannot wrap around the field.
    component slipBpsBits = Num2Bits(14);
    slipBpsBits.in <== max_slippage_bps;
    component slipBpsLte = LessEqThan(14);
    slipBpsLte.in[0] <== max_slippage_bps;
    slipBpsLte.in[1] <== 10000;
    slipBpsLte.out === 1;

    // ── Range checks on private inputs ──────────────────────────────
    // Without these, a malicious prover with witness control can pick
    // values that wrap mod the BN254 field — `signal_threshold *
    // price_first` (~constraint 4) and `(price_last - price_first) *
    // 10000` would alias, and the downstream Num2Bits(192) only catches
    // results that don't coincidentally fit in 192 bits. Pin the inputs
    // to realistic ranges: prices fit in 64 bits, threshold (bps) in 32,
    // stop-loss in 64.
    component priceBits[16];
    for (var pi = 0; pi < 16; pi++) {
        priceBits[pi] = Num2Bits(64);
        priceBits[pi].in <== price_observations[pi];
    }
    component thresholdBits = Num2Bits(32);
    thresholdBits.in <== signal_threshold;
    component stopLossBits = Num2Bits(64);
    stopLossBits.in <== stop_loss_price;

    // ── Constraint B: asset indices in range ────────────────────────
    // UNIVERSE_SIZE=8 → indices fit in 3 bits. Range-check + strict <.
    component inIdxBits  = Num2Bits(8);
    component outIdxBits = Num2Bits(8);
    inIdxBits.in  <== asset_in_idx;
    outIdxBits.in <== asset_out_idx;
    component inIdxLt  = LessThan(8);
    component outIdxLt = LessThan(8);
    inIdxLt.in[0]  <== asset_in_idx;
    inIdxLt.in[1]  <== UNIVERSE_SIZE;
    outIdxLt.in[0] <== asset_out_idx;
    outIdxLt.in[1] <== UNIVERSE_SIZE;
    inIdxLt.out  === 1;
    outIdxLt.out === 1;

    // HIGH #12 — explicitly forbid self-swaps. Without this, a prover
    // could pass asset_in == asset_out and the circuit would happily
    // attest a no-op trade that bypasses the strategy's intended risk
    // bounds (slippage / signal logic). yield_rotation_v1 has this
    // already; momentum + MR didn't.
    component sameIdx = IsEqual();
    sameIdx.in[0] <== asset_in_idx;
    sameIdx.in[1] <== asset_out_idx;
    sameIdx.out === 0;

    // HIGH #13 — explicit width on amount_in / min_amount_out /
    // max_position_size before they enter any quadratic constraint.
    // 128 bits is plenty of headroom for any realistic token amount
    // (uint128 ~ 3.4e38, vs USDC 6-decimal cap of ~1e30) but keeps
    // amount_in × (10000 - max_slippage_bps) well below the BN254
    // field size so a near-field-size witness can no longer wrap the
    // multiplication and still pass GreaterEqThan(160).
    component amountInBits = Num2Bits(128);
    amountInBits.in <== amount_in;
    component minOutBits = Num2Bits(128);
    minOutBits.in <== min_amount_out;
    component maxPosBits = Num2Bits(128);
    maxPosBits.in <== max_position_size;

    // ── Constraint 0: amount_in > 0 ─────────────────────────────────
    // Reject zero-amount entries (otherwise the proof is decorative —
    // a no-op trade can still pollute the attestation stream and the
    // reputation calc). Mirrors yield_rotation_v1.circom Constraint 7.
    signal amount_in_minus_one;
    amount_in_minus_one <== amount_in - 1;
    component amountInPositive = Num2Bits(128);
    amountInPositive.in <== amount_in_minus_one;

    // ── Constraint 1: amount_in <= max_position_size ────────────────
    component sizeOk = LessEqThan(128);
    sizeOk.in[0] <== amount_in;
    sizeOk.in[1] <== max_position_size;
    sizeOk.out === 1;

    // ── Constraint 2: slippage bound ────────────────────────────────
    // min_amount_out * 10000 >= amount_in * (10000 - max_slippage_bps)
    signal slipLhs;
    signal slipRhs;
    slipLhs <== min_amount_out * 10000;
    slipRhs <== amount_in * (10000 - max_slippage_bps);
    component slipOk = GreaterEqThan(160);
    slipOk.in[0] <== slipLhs;
    slipOk.in[1] <== slipRhs;
    slipOk.out === 1;

    // ── Constraint 3: chained Poseidon commitment to oracle root ────
    // h[0]   = Poseidon(obs[0])
    // h[i]   = Poseidon(h[i-1], obs[i])  for i in 1..15
    // h[15] === oracle_root
    component pos0 = Poseidon(1);
    pos0.inputs[0] <== price_observations[0];
    signal h[16];
    h[0] <== pos0.out;
    component posChain[15];
    for (var k = 1; k < 16; k++) {
        posChain[k - 1] = Poseidon(2);
        posChain[k - 1].inputs[0] <== h[k - 1];
        posChain[k - 1].inputs[1] <== price_observations[k];
        h[k] <== posChain[k - 1].out;
    }
    h[15] === oracle_root;

    // ── Constraint 4: direction-specific signal logic ───────────────
    is_long_entry  * (1 - is_long_entry)  === 0;
    is_short_entry * (1 - is_short_entry) === 0;
    is_exit        * (1 - is_exit)        === 0;
    is_long_entry + is_short_entry + is_exit === 1;
    // Bind to trade_direction: 0=exit, 1=long, 2=short.
    trade_direction === is_long_entry + 2 * is_short_entry;

    signal price_first;
    signal price_last;
    price_first <== price_observations[0];
    price_last  <== price_observations[15];

    // Pre-compute the signed momentum components, then mask by direction.
    signal up_delta_x10k;
    signal down_delta_x10k;
    signal threshold_x_pf;
    up_delta_x10k   <== (price_last - price_first) * 10000;
    down_delta_x10k <== (price_first - price_last) * 10000;
    threshold_x_pf  <== signal_threshold * price_first;

    // long_excess_raw  = up_delta_x10k   - threshold_x_pf  (must be >= 0 for long entry)
    // short_excess_raw = down_delta_x10k - threshold_x_pf  (must be >= 0 for short entry)
    signal long_excess_raw;
    signal short_excess_raw;
    long_excess_raw  <== up_delta_x10k   - threshold_x_pf;
    short_excess_raw <== down_delta_x10k - threshold_x_pf;

    // Mask by direction: non-active branch carries 0 (always passes the check).
    signal long_excess;
    signal short_excess;
    long_excess  <== is_long_entry  * long_excess_raw;
    short_excess <== is_short_entry * short_excess_raw;

    // Non-negativity via bit decomposition. 192b comfortably fits any realistic
    // price * 10000 in BN254 — prices are 64-bit, x10000 adds ~14 bits.
    component longNonNeg  = Num2Bits(192);
    component shortNonNeg = Num2Bits(192);
    longNonNeg.in  <== long_excess;
    shortNonNeg.in <== short_excess;

    // ── Constraint 5: block window bound ────────────────────────────
    signal windowDelta;
    windowDelta <== block_window_end - block_window_start;
    component windowOk = LessEqThan(64);
    windowOk.in[0] <== windowDelta;
    windowOk.in[1] <== 100;
    windowOk.out === 1;

    // ── Constraint 6: exit conditions (signal-flip OR stop-loss) ────
    is_signal_flip * (1 - is_signal_flip) === 0;
    is_stop_loss   * (1 - is_stop_loss)   === 0;
    // When exit: exactly one reason. When not exit: both 0.
    is_exit === is_signal_flip + is_stop_loss;

    // HIGH #11 — signal-flip exit must work for BOTH long and short
    // positions. The previous circuit only checked `down_delta -
    // threshold` which by construction can only justify exiting a
    // long; a short was uncloseable via flip. `was_long` (private,
    // boolean) selects the right delta direction at exit time. When
    // is_signal_flip = 0 the entire excess term is masked out and
    // was_long is unconstrained, so it doesn't add a witness burden
    // on entry / stop-loss tickets.
    was_long * (1 - was_long) === 0;
    signal sf_long_raw;
    signal sf_short_raw;
    sf_long_raw  <== down_delta_x10k - threshold_x_pf;
    sf_short_raw <== up_delta_x10k - threshold_x_pf;
    signal sf_long_term;
    signal sf_short_term;
    sf_long_term  <== was_long * sf_long_raw;
    sf_short_term <== (1 - was_long) * sf_short_raw;
    signal sf_excess_raw;
    sf_excess_raw <== sf_long_term + sf_short_term;
    signal sf_excess;
    sf_excess <== is_signal_flip * sf_excess_raw;
    component sfNonNeg = Num2Bits(192);
    sfNonNeg.in <== sf_excess;

    signal sl_excess_raw;
    sl_excess_raw <== stop_loss_price - price_last;
    signal sl_excess;
    sl_excess <== is_stop_loss * sl_excess_raw;
    component slNonNeg = Num2Bits(192);
    slNonNeg.in <== sl_excess;

    // ── Constraint 7: trade_hash binds public fields ────────────────
    // Including strategy_vault prevents replay onto a sibling vault that
    // happens to register the same momentum verifier.
    component tradePoseidon = Poseidon(10);
    tradePoseidon.inputs[0] <== strategy_vault;
    tradePoseidon.inputs[1] <== declared_class;
    tradePoseidon.inputs[2] <== params_hash;
    tradePoseidon.inputs[3] <== allocator_address;
    tradePoseidon.inputs[4] <== asset_in_idx;
    tradePoseidon.inputs[5] <== asset_out_idx;
    tradePoseidon.inputs[6] <== amount_in;
    tradePoseidon.inputs[7] <== min_amount_out;
    tradePoseidon.inputs[8] <== trade_direction;
    tradePoseidon.inputs[9] <== nonce;
    trade_hash === tradePoseidon.out;
}

// Phase 1 universe size: 8 assets per strategy manifest.
component main { public [
    trade_hash,
    declared_class,
    strategy_vault,
    params_hash,
    allocator_address,
    asset_in_idx,
    asset_out_idx,
    amount_in,
    min_amount_out,
    trade_direction,
    nonce,
    block_window_start,
    block_window_end,
    oracle_root
] } = MomentumV1(8);
