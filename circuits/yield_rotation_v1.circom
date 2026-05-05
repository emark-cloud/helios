pragma circom 2.1.9;

// Helios — yield_rotation_v1 strategy attestation circuit.
// Helios.md §9.4 (yield-rotation class) + phase2-plan.md WS1.C.
//
// Structurally distinct from the directional classes: no asset-pair swap,
// no slippage, no price observations. Proves that capital is moving
// between two allowlisted lending markets where the APY differential
// (net of bridging cost) exceeds an operator-declared threshold.
//
// Public-input layout (12 signals → adapter _PUBLIC_INPUT_COUNT = 12):
//
//   [0]  trade_hash             Poseidon(11) over all the other public
//                                 inputs. The on-chain side recomputes
//                                 the binding by checking each public
//                                 input directly (allocator, vault,
//                                 params_hash, allowlist_root, …) — so
//                                 a prover can't shift any field
//                                 without invalidating either the
//                                 trade_hash equality (in-circuit) or
//                                 the on-chain check.
//   [1]  declared_class
//   [2]  strategy_vault         on-chain `address(this)` equality check;
//                                 prevents cross-vault replay between
//                                 sibling YR vaults under the same
//                                 allocator.
//   [3]  params_hash            Poseidon(signal_threshold, bridging_cost).
//                                 Operator-set thresholds stay private,
//                                 but their commitment is public — the
//                                 vault checks against
//                                 `_activeParamsHash()` so the operator
//                                 can't tweak gates per-trade.
//   [4]  markets_allowlist_root registry-committed root over allowlisted
//                                 market ids; vault checks against
//                                 `StrategyRegistry.marketAllowlistRoot(class)`.
//   [5]  m_from                 market id capital is rotating out of
//   [6]  m_to                   market id capital is rotating into
//   [7]  amount_rotating        base-asset amount being moved
//   [8]  yield_oracle_root      Merkle root over (market_id, apy_bps)
//                                 leaves signed by the yield oracle
//   [9]  allocator_address
//   [10] nonce                  cross-vault dedup
//   [11] block_window_end       on-chain freshness gate (block.number ≤ this)
//
// Private witness:
//   apy_from, apy_to                 APY snapshots in bps (linked via the
//                                     yield-oracle Merkle proof)
//   signal_threshold                 minimum required differential, bps
//                                     (bound via params_hash PI)
//   bridging_cost                    operator-amortised bridging cost, bps
//                                     (bound via params_hash PI)
//   yield_path_from / yield_path_to  Merkle paths under yield_oracle_root
//   allow_path_from / allow_path_to  Merkle paths under markets_allowlist_root
//
// The yield-oracle leaf is Poseidon(market_id, apy_bps); the allowlist leaf
// is Poseidon(market_id). Tree depths are class-level constants — bumping
// either depth requires regenerating verifier artifacts.

include "circomlib/circuits/poseidon.circom";
include "circomlib/circuits/comparators.circom";
include "circomlib/circuits/bitify.circom";
include "circomlib/circuits/switcher.circom";

// Poseidon Merkle inclusion proof. `path_indices[i] == 0` means the
// sibling sits to the right at level i; `1` means it sits to the left.
template PoseidonMerkleProof(depth) {
    signal input leaf;
    signal input path_indices[depth];
    signal input siblings[depth];
    signal output root;

    signal current[depth + 1];
    current[0] <== leaf;

    component switchers[depth];
    component hashers[depth];

    for (var i = 0; i < depth; i++) {
        path_indices[i] * (1 - path_indices[i]) === 0;

        switchers[i] = Switcher();
        switchers[i].sel <== path_indices[i];
        switchers[i].L <== current[i];
        switchers[i].R <== siblings[i];

        hashers[i] = Poseidon(2);
        hashers[i].inputs[0] <== switchers[i].outL;
        hashers[i].inputs[1] <== switchers[i].outR;
        current[i + 1] <== hashers[i].out;
    }
    root <== current[depth];
}

// YIELD_DEPTH = 6  ⇒ up to 64 markets per yield-oracle snapshot.
// ALLOW_DEPTH = 4  ⇒ up to 16 markets in the registry allowlist.
template YieldRotationV1(YIELD_DEPTH, ALLOW_DEPTH) {
    // ── Public inputs ───────────────────────────────────────────────
    signal input trade_hash;
    signal input declared_class;
    signal input strategy_vault;
    signal input params_hash;
    signal input markets_allowlist_root;
    signal input m_from;
    signal input m_to;
    signal input amount_rotating;
    signal input yield_oracle_root;
    signal input allocator_address;
    signal input nonce;
    signal input block_window_end;
    signal input block_window_start;

    // ── Private witness ─────────────────────────────────────────────
    signal input apy_from;
    signal input apy_to;
    signal input signal_threshold;
    signal input bridging_cost;

    signal input yield_path_indices_from[YIELD_DEPTH];
    signal input yield_siblings_from[YIELD_DEPTH];
    signal input yield_path_indices_to[YIELD_DEPTH];
    signal input yield_siblings_to[YIELD_DEPTH];

    signal input allow_path_indices_from[ALLOW_DEPTH];
    signal input allow_siblings_from[ALLOW_DEPTH];
    signal input allow_path_indices_to[ALLOW_DEPTH];
    signal input allow_siblings_to[ALLOW_DEPTH];

    // ── Constraint 1: yield-oracle inclusion of (m_from, apy_from) ──
    component yieldLeafFrom = Poseidon(2);
    yieldLeafFrom.inputs[0] <== m_from;
    yieldLeafFrom.inputs[1] <== apy_from;

    component yieldProofFrom = PoseidonMerkleProof(YIELD_DEPTH);
    yieldProofFrom.leaf <== yieldLeafFrom.out;
    for (var i = 0; i < YIELD_DEPTH; i++) {
        yieldProofFrom.path_indices[i] <== yield_path_indices_from[i];
        yieldProofFrom.siblings[i] <== yield_siblings_from[i];
    }
    yieldProofFrom.root === yield_oracle_root;

    // ── Constraint 2: yield-oracle inclusion of (m_to, apy_to) ──────
    component yieldLeafTo = Poseidon(2);
    yieldLeafTo.inputs[0] <== m_to;
    yieldLeafTo.inputs[1] <== apy_to;

    component yieldProofTo = PoseidonMerkleProof(YIELD_DEPTH);
    yieldProofTo.leaf <== yieldLeafTo.out;
    for (var i = 0; i < YIELD_DEPTH; i++) {
        yieldProofTo.path_indices[i] <== yield_path_indices_to[i];
        yieldProofTo.siblings[i] <== yield_siblings_to[i];
    }
    yieldProofTo.root === yield_oracle_root;

    // ── Constraint 3: allowlist inclusion of m_from ─────────────────
    component allowLeafFrom = Poseidon(1);
    allowLeafFrom.inputs[0] <== m_from;

    component allowProofFrom = PoseidonMerkleProof(ALLOW_DEPTH);
    allowProofFrom.leaf <== allowLeafFrom.out;
    for (var i = 0; i < ALLOW_DEPTH; i++) {
        allowProofFrom.path_indices[i] <== allow_path_indices_from[i];
        allowProofFrom.siblings[i] <== allow_siblings_from[i];
    }
    allowProofFrom.root === markets_allowlist_root;

    // ── Constraint 4: allowlist inclusion of m_to ───────────────────
    component allowLeafTo = Poseidon(1);
    allowLeafTo.inputs[0] <== m_to;

    component allowProofTo = PoseidonMerkleProof(ALLOW_DEPTH);
    allowProofTo.leaf <== allowLeafTo.out;
    for (var i = 0; i < ALLOW_DEPTH; i++) {
        allowProofTo.path_indices[i] <== allow_path_indices_to[i];
        allowProofTo.siblings[i] <== allow_siblings_to[i];
    }
    allowProofTo.root === markets_allowlist_root;

    // ── Constraint 5: m_from ≠ m_to ─────────────────────────────────
    // Trivially-non-rotating trades are rejected.
    signal market_diff;
    signal market_diff_inv;
    market_diff <== m_to - m_from;
    market_diff_inv <-- 1 / market_diff;
    market_diff * market_diff_inv === 1;

    // ── Constraint 6: APY differential beats threshold + bridging ───
    // (apy_to − apy_from) ≥ signal_threshold + bridging_cost
    // Range checks keep the field math honest:
    //   apy_*, signal_threshold, bridging_cost all bounded by 16-bit bps
    //   (max realistic APY ≈ 100% = 10 000 bps; cap at 2¹⁶ = 65 535).
    component apyFromBits = Num2Bits(16);
    component apyToBits = Num2Bits(16);
    component thresholdBits = Num2Bits(16);
    component bridgingBits = Num2Bits(16);
    apyFromBits.in <== apy_from;
    apyToBits.in <== apy_to;
    thresholdBits.in <== signal_threshold;
    bridgingBits.in <== bridging_cost;

    signal differential;
    differential <== apy_to - apy_from - signal_threshold - bridging_cost;

    // differential ≥ 0 via Num2Bits(32) (worst-case ~17 bits).
    component diffNonNeg = Num2Bits(32);
    diffNonNeg.in <== differential;

    // ── Constraint 7: amount_rotating > 0 ───────────────────────────
    // Reject zero-amount rotations (otherwise the proof is decorative).
    component amountBits = Num2Bits(128);
    amountBits.in <== amount_rotating;
    signal amount_minus_one;
    amount_minus_one <== amount_rotating - 1;
    component amountPositive = Num2Bits(128);
    amountPositive.in <== amount_minus_one;

    // ── Constraint 8: params_hash binding ───────────────────────────
    // params_hash = Poseidon(signal_threshold, bridging_cost). The vault
    // checks the public params_hash against `_activeParamsHash()` (the
    // registry-committed value, set via commitInitialParamsHash /
    // rotateParams). Operators cannot loosen the threshold or fudge the
    // bridging cost on a per-trade basis without rotating the manifest.
    component paramsPoseidon = Poseidon(2);
    paramsPoseidon.inputs[0] <== signal_threshold;
    paramsPoseidon.inputs[1] <== bridging_cost;
    params_hash === paramsPoseidon.out;

    // ── Constraint 8b: block-window bound ───────────────────────────
    // Mirror momentum/MR: cap the [start, end] interval to ≤100 blocks
    // so a pre-attested proof cannot remain replayable across an
    // arbitrarily wide window. Without `block_window_start` as a PI,
    // any proof minted before the registered yield-oracle root could
    // be replayed for the entire pre-attestation lifetime — review
    // followup #5.
    signal yrWindowDelta;
    yrWindowDelta <== block_window_end - block_window_start;
    component yrWindowOk = LessEqThan(64);
    yrWindowOk.in[0] <== yrWindowDelta;
    yrWindowOk.in[1] <== 100;
    yrWindowOk.out === 1;

    // ── Constraint 9: trade_hash binding ────────────────────────────
    // trade_hash = Poseidon(12) over the canonical public-input tuple
    // (everything but trade_hash itself). Each component is also checked
    // independently on-chain (vault, allocator, params, allowlist, …) so
    // the prover cannot substitute a fresh proof for a different vault
    // while keeping the same trade_hash.
    component tradePoseidon = Poseidon(12);
    tradePoseidon.inputs[0] <== declared_class;
    tradePoseidon.inputs[1] <== strategy_vault;
    tradePoseidon.inputs[2] <== params_hash;
    tradePoseidon.inputs[3] <== markets_allowlist_root;
    tradePoseidon.inputs[4] <== m_from;
    tradePoseidon.inputs[5] <== m_to;
    tradePoseidon.inputs[6] <== amount_rotating;
    tradePoseidon.inputs[7] <== yield_oracle_root;
    tradePoseidon.inputs[8] <== allocator_address;
    tradePoseidon.inputs[9] <== nonce;
    tradePoseidon.inputs[10] <== block_window_end;
    tradePoseidon.inputs[11] <== block_window_start;
    trade_hash === tradePoseidon.out;
}

component main { public [
    trade_hash,
    declared_class,
    strategy_vault,
    params_hash,
    markets_allowlist_root,
    m_from,
    m_to,
    amount_rotating,
    yield_oracle_root,
    allocator_address,
    nonce,
    block_window_end,
    block_window_start
] } = YieldRotationV1(6, 4);
