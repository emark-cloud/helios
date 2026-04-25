// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

/// @notice Wraps the per-class Groth16 verifier. Per-chain deploy.
///         Helios.md §6.7.
interface ITradeAttestationVerifier {
    event VerifierRegistered(bytes32 indexed declaredClass, address verifier);

    error UnknownClass();

    function verify(
        bytes32 declaredClass,
        bytes calldata proof,
        uint256[] calldata publicInputs
    ) external view returns (bool);

    function verifierOf(bytes32 declaredClass) external view returns (address);
    function registerVerifier(bytes32 declaredClass, address verifier) external;
}

/// @notice Minimal shape every class-specific Groth16 verifier contract exposes.
///         snarkjs generates this signature by default (we rename the contract in Makefile).
interface IGroth16Verifier {
    function verifyProof(
        uint256[2] calldata a,
        uint256[2][2] calldata b,
        uint256[2] calldata c,
        uint256[] calldata publicInputs
    ) external view returns (bool);
}
