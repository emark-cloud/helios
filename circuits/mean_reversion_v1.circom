pragma circom 2.1.9;

// Helios — mean_reversion_v1 strategy attestation circuit.
// Helios.md §9.4 (mean-reversion class) + phase2-plan.md WS1.B.
//
// Public-input layout matches momentum_v1 (14 signals) so the StrategyVault
// PI_* constants and the verifier-adapter _PUBLIC_INPUT_COUNT are reused
// unchanged. The semantic difference is the signal logic:
//   - long entry  := price_last is at least n_sigma below the 16-bar mean
//   - short entry := price_last is at least n_sigma above the 16-bar mean
//   - exit        := mean re-cross (deviation magnitude has fallen below
//                    threshold) OR stop-loss
//
// Stddev is avoided via squared-form comparisons. With:
//     sum   = Σ price_observations[i]
//     d_i   = price[i] − mean = (16·price[i] − sum) / 16
//     dev16[i] = 16·price[i] − sum                       = 16·d_i
//     dev_last_sq = dev16[15]²                           = 256·d_15²
//     sum_sq_devs = Σ dev16[i]²                          = 256·Σd_i² = 4096·variance
// the entry magnitude check d_15² > N²·variance becomes:
//     256·d_15² · 16 > N² · 4096·variance · (256/4096)
//     ⇔ dev_last_sq · 16 > N² · sum_sq_devs
// with N expressed as `signal_threshold / 100` (n_sigma_x100):
//     160 000 · dev_last_sq ≥ signal_threshold² · sum_sq_devs
//
// The `signal_threshold` slot of the params_hash is reused — semantically
// it is `n_sigma_x100` (e.g. 200 ⇒ 2.00σ). Field positions in
// params_hash and trade_hash are unchanged so the on-chain manifest
// schema works for both classes.

include "circomlib/circuits/poseidon.circom";
include "circomlib/circuits/comparators.circom";
include "circomlib/circuits/bitify.circom";

template MeanReversionV1(UNIVERSE_SIZE) {
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
    signal input max_position_size;
    signal input max_slippage_bps;
    signal input signal_threshold;      // n_sigma_x100 (e.g. 200 ⇒ 2.00σ)
    signal input stop_loss_price;
    signal input price_observations[16];

    signal input is_long_entry;
    signal input is_short_entry;
    signal input is_exit;

    signal input is_signal_flip;
    signal input is_stop_loss;

    // ── Constraint A: params_hash binds operator-declared parameters ─
    component paramsPoseidon = Poseidon(4);
    paramsPoseidon.inputs[0] <== max_position_size;
    paramsPoseidon.inputs[1] <== max_slippage_bps;
    paramsPoseidon.inputs[2] <== signal_threshold;
    paramsPoseidon.inputs[3] <== stop_loss_price;
    params_hash === paramsPoseidon.out;

    component slipBpsBits = Num2Bits(14);
    slipBpsBits.in <== max_slippage_bps;
    component slipBpsLte = LessEqThan(14);
    slipBpsLte.in[0] <== max_slippage_bps;
    slipBpsLte.in[1] <== 10000;
    slipBpsLte.out === 1;

    // ── Range checks on private inputs ──────────────────────────────
    // Mean-reversion squares the deviations (16·price - sum)², so a
    // malicious prover with witness control could grind unrealistic
    // prices to wrap the field and bypass the downstream Num2Bits(192).
    // Pin price intake to 64 bits and the n_sigma_x100 threshold to 32.
    // stop_loss_price feeds the exit-side stop-loss check.
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

    // ── Constraint 1: amount_in <= max_position_size ────────────────
    component sizeOk = LessEqThan(128);
    sizeOk.in[0] <== amount_in;
    sizeOk.in[1] <== max_position_size;
    sizeOk.out === 1;

    // ── Constraint 2: slippage bound ────────────────────────────────
    signal slipLhs;
    signal slipRhs;
    slipLhs <== min_amount_out * 10000;
    slipRhs <== amount_in * (10000 - max_slippage_bps);
    component slipOk = GreaterEqThan(160);
    slipOk.in[0] <== slipLhs;
    slipOk.in[1] <== slipRhs;
    slipOk.out === 1;

    // ── Constraint 3: chained Poseidon commitment to oracle root ────
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

    // ── Direction selectors ─────────────────────────────────────────
    is_long_entry  * (1 - is_long_entry)  === 0;
    is_short_entry * (1 - is_short_entry) === 0;
    is_exit        * (1 - is_exit)        === 0;
    is_long_entry + is_short_entry + is_exit === 1;
    trade_direction === is_long_entry + 2 * is_short_entry;

    // ── Mean / deviation pre-computation ────────────────────────────
    // sum_total = Σ price_observations
    var sumExpr = 0;
    for (var i = 0; i < 16; i++) {
        sumExpr += price_observations[i];
    }
    signal sum_total;
    sum_total <== sumExpr;

    // dev16[i] = 16·price[i] − sum_total. Linear in inputs.
    signal dev16[16];
    for (var i = 0; i < 16; i++) {
        dev16[i] <== 16 * price_observations[i] - sum_total;
    }

    // dev_sq[i] = dev16[i]². 16 quadratic constraints.
    signal dev_sq[16];
    for (var i = 0; i < 16; i++) {
        dev_sq[i] <== dev16[i] * dev16[i];
    }

    // sum_sq_devs = Σ dev_sq[i].
    var sumSqExpr = 0;
    for (var i = 0; i < 16; i++) {
        sumSqExpr += dev_sq[i];
    }
    signal sum_sq_devs;
    sum_sq_devs <== sumSqExpr;

    // dev_last_sq = dev16[15]² (re-bound for readability).
    signal dev_last_sq;
    dev_last_sq <== dev_sq[15];

    // signal_threshold² — quadratic.
    signal threshold_sq;
    threshold_sq <== signal_threshold * signal_threshold;

    // RHS = signal_threshold² · sum_sq_devs.
    signal rhs;
    rhs <== threshold_sq * sum_sq_devs;

    // LHS = 160 000 · dev_last_sq (linear by constant).
    signal lhs;
    lhs <== 160000 * dev_last_sq;

    // ── Constraint 4a: entry magnitude (long OR short) ──────────────
    // For an entry, 160 000·dev_last_sq ≥ signal_threshold²·sum_sq_devs
    // (i.e. lhs ≥ rhs). Enforced only on entry directions.
    signal is_entry;
    is_entry <== is_long_entry + is_short_entry;
    signal entry_excess_raw;
    entry_excess_raw <== lhs - rhs;
    signal entry_excess;
    entry_excess <== is_entry * entry_excess_raw;

    // 192 bits: lhs ≤ 1.6·10⁵ · 2¹⁵⁰ ≈ 2¹⁶⁷, rhs ≤ 2²⁰·2¹⁵⁵ ≈ 2¹⁷⁵; both fit.
    component entryNonNeg = Num2Bits(192);
    entryNonNeg.in <== entry_excess;

    // ── Constraint 4b: entry sign (long ⇒ price below mean) ─────────
    // long entry: sum_total ≥ 16·price_last  ⇔  −dev16[15] ≥ 0
    signal long_sign_raw;
    long_sign_raw <== sum_total - 16 * price_observations[15];
    signal long_sign;
    long_sign <== is_long_entry * long_sign_raw;
    component longSignNonNeg = Num2Bits(80);
    longSignNonNeg.in <== long_sign;

    // short entry: 16·price_last ≥ sum_total  ⇔  dev16[15] ≥ 0
    signal short_sign_raw;
    short_sign_raw <== 16 * price_observations[15] - sum_total;
    signal short_sign;
    short_sign <== is_short_entry * short_sign_raw;
    component shortSignNonNeg = Num2Bits(80);
    shortSignNonNeg.in <== short_sign;

    // ── Constraint 5: block window bound ────────────────────────────
    signal windowDelta;
    windowDelta <== block_window_end - block_window_start;
    component windowOk = LessEqThan(64);
    windowOk.in[0] <== windowDelta;
    windowOk.in[1] <== 100;
    windowOk.out === 1;

    // ── Constraint 6: exit conditions (signal-flip OR stop-loss) ────
    // signal_flip := mean re-cross := deviation magnitude has fallen
    // below the entry threshold, i.e. lhs ≤ rhs (rhs ≥ lhs).
    is_signal_flip * (1 - is_signal_flip) === 0;
    is_stop_loss   * (1 - is_stop_loss)   === 0;
    is_exit === is_signal_flip + is_stop_loss;

    signal flip_excess_raw;
    flip_excess_raw <== rhs - lhs;
    signal flip_excess;
    flip_excess <== is_signal_flip * flip_excess_raw;
    component flipNonNeg = Num2Bits(192);
    flipNonNeg.in <== flip_excess;

    signal sl_excess_raw;
    sl_excess_raw <== stop_loss_price - price_observations[15];
    signal sl_excess;
    sl_excess <== is_stop_loss * sl_excess_raw;
    component slNonNeg = Num2Bits(192);
    slNonNeg.in <== sl_excess;

    // ── Constraint 7: trade_hash binds public fields ────────────────
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
] } = MeanReversionV1(8);
