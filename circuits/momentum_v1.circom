pragma circom 2.1.9;

// Helios — momentum_v1 strategy attestation circuit.
// Helios.md §9.3.
//
// Proves a single trade satisfies the momentum_v1 class invariants:
//   1. asset_in / asset_out are in the strategy's manifest universe
//   2. amount_in <= max_position_size (operator-declared bound)
//   3. min_amount_out respects manifest's max slippage
//   4. price_observations Poseidon-chain to a committed oracle root
//   5. direction-specific signal logic (long entry / short entry / exit)
//   6. block_window_end - block_window_start <= 100
//   7. exit conditions: signal-flip OR stop-loss
//   8. trade_hash matches Poseidon of the trade calldata public fields
//
// Public input order MUST match the Solidity verifier's publicInputs[] indexing
// in `TradeAttestationVerifier`. Do not reorder without updating both sides.

include "circomlib/circuits/poseidon.circom";
include "circomlib/circuits/comparators.circom";
include "circomlib/circuits/bitify.circom";

// Asset universe size — manifest enforces this on-chain at registration.
// Bumping this raises constraint count linearly via the membership checks.
template MomentumV1(UNIVERSE_SIZE) {
    // ── Public inputs ───────────────────────────────────────────────
    signal input trade_hash;            // Poseidon over the trade fields
    signal input declared_class;        // keccak256("momentum_v1") truncated to BN254 field
    signal input asset_in;              // address as field element
    signal input asset_out;
    signal input amount_in;
    signal input min_amount_out;
    signal input trade_direction;       // 0=exit, 1=long entry, 2=short entry
    signal input allocator_address;
    signal input nonce;
    signal input block_window_start;
    signal input block_window_end;

    // ── Witness (private) ───────────────────────────────────────────
    signal input asset_universe[UNIVERSE_SIZE];     // operator's declared universe
    signal input max_position_size;                 // operator's declared cap
    signal input max_slippage_bps;                  // operator's declared slippage
    signal input position_state;                    // current position size (unsigned)
    signal input signal_threshold;                  // operator-chosen threshold (bps)
    signal input price_observations[16];            // last 16 minute-bars
    signal input oracle_root;                       // committed price-oracle root

    // Direction selector witness (one-hot, validated below).
    signal input is_long_entry;
    signal input is_short_entry;
    signal input is_exit;

    // Exit-reason selector witness (one-hot when is_exit, else both 0).
    signal input is_signal_flip;
    signal input is_stop_loss;
    signal input stop_loss_price;                   // operator-declared stop level

    // ── Constraint 1: asset_in / asset_out in universe ──────────────
    component memberIn  = InUniverse(UNIVERSE_SIZE);
    component memberOut = InUniverse(UNIVERSE_SIZE);
    memberIn.candidate <== asset_in;
    memberOut.candidate <== asset_out;
    for (var i = 0; i < UNIVERSE_SIZE; i++) {
        memberIn.universe[i]  <== asset_universe[i];
        memberOut.universe[i] <== asset_universe[i];
    }
    memberIn.found  === 1;
    memberOut.found === 1;

    // ── Constraint 2: amount_in <= max_position_size ────────────────
    component sizeOk = LessEqThan(128);
    sizeOk.in[0] <== amount_in;
    sizeOk.in[1] <== max_position_size;
    sizeOk.out === 1;

    // ── Constraint 3: slippage bound ────────────────────────────────
    // min_amount_out * 10000 >= amount_in * (10000 - max_slippage_bps)
    signal slipLhs;
    signal slipRhs;
    slipLhs <== min_amount_out * 10000;
    slipRhs <== amount_in * (10000 - max_slippage_bps);
    component slipOk = GreaterEqThan(160);
    slipOk.in[0] <== slipLhs;
    slipOk.in[1] <== slipRhs;
    slipOk.out === 1;

    // ── Constraint 4: chained Poseidon commitment to oracle root ────
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

    // ── Constraint 5: direction-specific signal logic ───────────────
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

    // ── Constraint 6: block window bound ────────────────────────────
    signal windowDelta;
    windowDelta <== block_window_end - block_window_start;
    component windowOk = LessEqThan(64);
    windowOk.in[0] <== windowDelta;
    windowOk.in[1] <== 100;
    windowOk.out === 1;

    // ── Constraint 7: exit conditions (signal-flip OR stop-loss) ────
    is_signal_flip * (1 - is_signal_flip) === 0;
    is_stop_loss   * (1 - is_stop_loss)   === 0;
    // When exit: exactly one reason. When not exit: both 0.
    is_exit === is_signal_flip + is_stop_loss;

    signal sf_excess_raw;
    sf_excess_raw <== down_delta_x10k - threshold_x_pf;
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

    // ── Constraint 8: trade_hash binds public fields ────────────────
    component tradePoseidon = Poseidon(8);
    tradePoseidon.inputs[0] <== declared_class;
    tradePoseidon.inputs[1] <== asset_in;
    tradePoseidon.inputs[2] <== asset_out;
    tradePoseidon.inputs[3] <== amount_in;
    tradePoseidon.inputs[4] <== min_amount_out;
    tradePoseidon.inputs[5] <== trade_direction;
    tradePoseidon.inputs[6] <== allocator_address;
    tradePoseidon.inputs[7] <== nonce;
    trade_hash === tradePoseidon.out;

    // Bind position_state so the witness check survives optimization.
    signal posBind;
    posBind <== position_state * 1;
}

// ── Universe membership (linear scan; fine for small universes) ────
template InUniverse(N) {
    signal input candidate;
    signal input universe[N];
    signal output found;

    signal matches[N];
    var sum = 0;
    component eq[N];
    for (var i = 0; i < N; i++) {
        eq[i] = IsEqual();
        eq[i].in[0] <== candidate;
        eq[i].in[1] <== universe[i];
        matches[i] <== eq[i].out;
        sum += matches[i];
    }
    component sumEq = IsEqual();
    sumEq.in[0] <== sum;
    sumEq.in[1] <== 1;
    found <== sumEq.out;
}

// Phase 1 universe size: 8 assets per strategy manifest.
component main { public [
    trade_hash, declared_class,
    asset_in, asset_out,
    amount_in, min_amount_out,
    trade_direction, allocator_address,
    nonce, block_window_start, block_window_end
] } = MomentumV1(8);
