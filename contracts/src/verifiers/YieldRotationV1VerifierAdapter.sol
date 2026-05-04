// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { IGroth16Verifier } from "../interfaces/ITradeAttestationVerifier.sol";

/// @notice Bridges snarkjs's fixed-size verifier signature
///         (`verifyProof(uint[2], uint[2][2], uint[2], uint[12])`) for
///         yield_rotation_v1 onto the dynamic-array `IGroth16Verifier` shape
///         that `TradeAttestationVerifier` calls. YR uses a distinct 12-PI
///         layout (rotation rather than swap), so it ships a dedicated
///         entry path in `StrategyVault`. The trade_hash binds
///         `strategy_vault`, `params_hash`, and `markets_allowlist_root`
///         alongside the rotation fields — the vault recomputes nothing,
///         it just enforces each PI matches an authoritative on-chain
///         source (vault address, registry params hash, registry
///         allowlist root). See yield_rotation_v1.circom for the full
///         binding.
interface ISnarkjsYieldRotationV1Verifier {
    function verifyProof(
        uint256[2] calldata a,
        uint256[2][2] calldata b,
        uint256[2] calldata c,
        uint256[12] calldata publicSignals
    ) external view returns (bool);
}

contract YieldRotationV1VerifierAdapter is IGroth16Verifier {
    uint256 private constant _PUBLIC_INPUT_COUNT = 12;

    ISnarkjsYieldRotationV1Verifier public immutable inner;

    error WrongPublicInputCount(uint256 got, uint256 expected);

    constructor(address inner_) {
        inner = ISnarkjsYieldRotationV1Verifier(inner_);
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
        uint256[12] memory fixedInputs;
        for (uint256 i = 0; i < _PUBLIC_INPUT_COUNT; i++) {
            fixedInputs[i] = publicInputs[i];
        }
        return inner.verifyProof(a, b, c, fixedInputs);
    }
}
