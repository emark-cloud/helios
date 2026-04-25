pragma circom 2.1.9;

// Helios — momentum_v1 strategy attestation circuit.
// Helios.md §9.3.
//
// Proves a single trade satisfies the momentum_v1 class invariants:
//   1. asset_in / asset_out are in the strategy's manifest universe
//   2. amount_in <= max_position_size (operator-declared bound)
//   3. min_amount_out respects manifest's max slippage
//   4. price_observations Poseidon-chain to a committed oracle root        (TODO)
//   5. direction-specific signal logic (long entry / short entry / exit)   (TODO)
//   6. block_window_end - block_window_start <= 100
//   7. trade_hash matches Poseidon of the trade calldata public fields
//
// Scaffolding pass — constraints 1, 2, 3, 6, 7 implemented; 4 and 5 stubbed
// with structural placeholders so constraint count is visible while the
// signal/oracle subcomponents are being designed.
//
// Public input order MUST match the Solidity verifier's publicInputs[] indexing
// in `TradeAttestationVerifier`. Do not reorder without updating both sides.

include "circomlib/circuits/poseidon.circom";
include "circomlib/circuits/comparators.circom";

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
    signal input trade_direction;       // 0=exit, 1=long, 2=short
    signal input allocator_address;
    signal input nonce;
    signal input block_window_start;
    signal input block_window_end;

    // ── Witness (private) ───────────────────────────────────────────
    signal input asset_universe[UNIVERSE_SIZE];     // operator's declared universe
    signal input max_position_size;                 // operator's declared cap
    signal input max_slippage_bps;                  // operator's declared slippage
    signal input position_state;                    // current position (signed encoding)
    signal input signal_threshold;                  // operator-chosen threshold
    signal input price_observations[16];            // last 16 minute-bars
    signal input oracle_root;                       // committed price-oracle root

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
    component sizeOk = LessEqThan(128);             // 128-bit amounts
    sizeOk.in[0] <== amount_in;
    sizeOk.in[1] <== max_position_size;
    sizeOk.out === 1;

    // ── Constraint 3: slippage bound ────────────────────────────────
    // min_amount_out * 10000 >= amount_in * (10000 - max_slippage_bps)
    // Rearranged to avoid division.
    signal lhs;
    signal rhs;
    lhs <== min_amount_out * 10000;
    rhs <== amount_in * (10000 - max_slippage_bps);
    component slipOk = GreaterEqThan(160);
    slipOk.in[0] <== lhs;
    slipOk.in[1] <== rhs;
    slipOk.out === 1;

    // ── Constraint 4: Poseidon-chain commitment to oracle root ──────
    // TODO: chain Poseidon(prev || obs[i]) across price_observations and
    // assert the final hash equals oracle_root. For this scaffold we just
    // bind the witness with a single Poseidon over the array so the root
    // is constrained to a deterministic function of the observations.
    component poseidonChain = Poseidon(16);
    for (var j = 0; j < 16; j++) {
        poseidonChain.inputs[j] <== price_observations[j];
    }
    poseidonChain.out === oracle_root;

    // ── Constraint 5: direction-specific signal logic ───────────────
    // TODO: full implementation needs:
    //   - N-period return computed from price_observations
    //   - long entry: return > signal_threshold AND position_state <= 0
    //   - short entry: return < -signal_threshold AND position_state >= 0
    //   - exit: signal-flip OR stop-loss true
    // For this scaffold we bind direction to 0/1/2 to expose the placeholder
    // gate and let downstream logic plug in.
    component dirRange = LessEqThan(8);
    dirRange.in[0] <== trade_direction;
    dirRange.in[1] <== 2;
    dirRange.out === 1;

    // Reference the witness signals so they aren't optimized out before the
    // real signal/threshold logic lands.
    signal dirCheck;
    dirCheck <== signal_threshold * trade_direction;

    // ── Constraint 6: block window bound ────────────────────────────
    signal windowDelta;
    windowDelta <== block_window_end - block_window_start;
    component windowOk = LessEqThan(64);
    windowOk.in[0] <== windowDelta;
    windowOk.in[1] <== 100;
    windowOk.out === 1;

    // ── Constraint 7: trade_hash binds public fields ────────────────
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
    // Exactly one match => candidate is in universe and unique.
    // (At-least-one is enforced by manifest dedupe at registration.)
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
