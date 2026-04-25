// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { IGroth16Verifier } from "../interfaces/ITradeAttestationVerifier.sol";

/// @notice Bridges snarkjs's fixed-size verifier signature
///         (`verifyProof(uint[2], uint[2][2], uint[2], uint[N])`) onto the
///         dynamic-array `IGroth16Verifier` shape that
///         `TradeAttestationVerifier` calls. One adapter per class — the
///         constant `_PUBLIC_INPUT_COUNT` matches the circuit's public
///         signal count (momentum_v1 = 11; mean_reversion_v1 / yield_rotation_v1
///         get their own adapters with their own counts).
interface ISnarkjsMomentumV1Verifier {
    function verifyProof(
        uint256[2] calldata a,
        uint256[2][2] calldata b,
        uint256[2] calldata c,
        uint256[11] calldata publicSignals
    ) external view returns (bool);
}

contract MomentumV1VerifierAdapter is IGroth16Verifier {
    uint256 private constant _PUBLIC_INPUT_COUNT = 11;

    ISnarkjsMomentumV1Verifier public immutable inner;

    error WrongPublicInputCount(uint256 got, uint256 expected);

    constructor(address inner_) {
        inner = ISnarkjsMomentumV1Verifier(inner_);
    }

    function verifyProof(
        uint256[2] calldata a,
        uint256[2][2] calldata b,
        uint256[2] calldata c,
        uint256[] calldata publicInputs
    ) external view returns (bool) {
        if (publicInputs.length != _PUBLIC_INPUT_COUNT) {
            revert WrongPublicInputCount(publicInputs.length, _PUBLIC_INPUT_COUNT);
        }
        uint256[11] memory fixedInputs;
        for (uint256 i = 0; i < _PUBLIC_INPUT_COUNT; i++) {
            fixedInputs[i] = publicInputs[i];
        }
        return inner.verifyProof(a, b, c, fixedInputs);
    }
}
