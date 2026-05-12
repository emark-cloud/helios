// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { IGroth16Verifier } from "../interfaces/ITradeAttestationVerifier.sol";

/// @notice Bridges snarkjs's fixed-size verifier signature
///         (`verifyProof(uint[2], uint[2][2], uint[2], uint[16])`) for
///         mean_reversion_v1 onto the dynamic-array `IGroth16Verifier`
///         shape that `TradeAttestationVerifier` calls. Mean-rev shares
///         momentum's PI layout (see `StrategyVault.PI_*` constants).
///         Bumped 14 → 16 by the Phase-6 cross-decimal slippage
///         redesign: `pow10_asset_in` and `pow10_asset_out` join the
///         public-input vector so `StrategyVault.executeWithProof` can
///         bind them to the live `IERC20.decimals()` of the universe-
///         asset entries before delegating to the verifier.
interface ISnarkjsMeanReversionV1Verifier {
    function verifyProof(
        uint256[2] calldata a,
        uint256[2][2] calldata b,
        uint256[2] calldata c,
        uint256[16] calldata publicSignals
    ) external view returns (bool);
}

contract MeanReversionV1VerifierAdapter is IGroth16Verifier {
    uint256 private constant _PUBLIC_INPUT_COUNT = 16;

    ISnarkjsMeanReversionV1Verifier public immutable inner;

    error WrongPublicInputCount(uint256 got, uint256 expected);

    constructor(address inner_) {
        inner = ISnarkjsMeanReversionV1Verifier(inner_);
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
        uint256[16] memory fixedInputs;
        for (uint256 i = 0; i < _PUBLIC_INPUT_COUNT; i++) {
            fixedInputs[i] = publicInputs[i];
        }
        return inner.verifyProof(a, b, c, fixedInputs);
    }
}
