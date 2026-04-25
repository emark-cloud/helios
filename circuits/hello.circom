pragma circom 2.1.9;

// Helios — Phase 0 hello circuit.
//
// Trivial circuit that proves the prover knows `a, b` such that `a * b == c`,
// with `c` as a public input. Used purely to verify the Circom/snarkjs/Solidity
// verifier pipeline works end-to-end before Phase 1 momentum_v1 lands.
//
// Constraint count: ~1. Proof time: instant.
template Hello() {
    signal input a;
    signal input b;
    signal input c;

    signal product;
    product <== a * b;
    product === c;
}

component main { public [c] } = Hello();
