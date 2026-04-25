// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { IGroth16Verifier } from "../../src/interfaces/ITradeAttestationVerifier.sol";

/// @notice Test verifier whose answer is configurable so we can exercise
///         both true/false dispatch paths without generating real proofs.
contract MockGroth16Verifier is IGroth16Verifier {
    bool public answer;

    constructor(bool answer_) {
        answer = answer_;
    }

    function setAnswer(bool a) external {
        answer = a;
    }

    function verifyProof(
        uint256[2] calldata,
        uint256[2][2] calldata,
        uint256[2] calldata,
        uint256[] calldata
    ) external view returns (bool) {
        return answer;
    }
}
