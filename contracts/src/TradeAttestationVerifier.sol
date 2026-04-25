// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Ownable } from "@openzeppelin/contracts/access/Ownable.sol";

import {
    ITradeAttestationVerifier,
    IGroth16Verifier
} from "./interfaces/ITradeAttestationVerifier.sol";

/// @title TradeAttestationVerifier
/// @notice Per-class Groth16 verifier dispatch. Each strategy class
///         (momentum_v1, mean_reversion_v1, yield_rotation_v1, ...) has its
///         own snarkjs-generated verifier registered here. StrategyVault
///         calls verify(class, proof, publicInputs) and reverts if false.
///         Helios.md §6.7.
contract TradeAttestationVerifier is ITradeAttestationVerifier, Ownable {
    mapping(bytes32 => address) public verifierByClassMap;

    error ZeroAddress();

    constructor(address owner_) Ownable(owner_) { }

    function registerVerifier(bytes32 declaredClass, address verifier) external onlyOwner {
        if (verifier == address(0)) revert ZeroAddress();
        verifierByClassMap[declaredClass] = verifier;
        emit VerifierRegistered(declaredClass, verifier);
    }

    function verifierOf(bytes32 declaredClass) external view returns (address) {
        return verifierByClassMap[declaredClass];
    }

    /// @notice The proof bytes encode the Groth16 (a, b, c) tuple as packed
    ///         uint256s in the order snarkjs emits: a[2] || b[2][2] || c[2].
    ///         Length therefore must be 8 * 32 = 256 bytes.
    function verify(bytes32 declaredClass, bytes calldata proof, uint256[] calldata publicInputs)
        external
        view
        returns (bool)
    {
        address verifier = verifierByClassMap[declaredClass];
        if (verifier == address(0)) revert UnknownClass();

        (uint256[2] memory a, uint256[2][2] memory b, uint256[2] memory c) = _decodeProof(proof);

        return IGroth16Verifier(verifier).verifyProof(a, b, c, publicInputs);
    }

    function _decodeProof(bytes calldata proof)
        internal
        pure
        returns (uint256[2] memory a, uint256[2][2] memory b, uint256[2] memory c)
    {
        require(proof.length == 256, "TradeAttestationVerifier: bad proof length");
        (a, b, c) = abi.decode(proof, (uint256[2], uint256[2][2], uint256[2]));
    }
}
