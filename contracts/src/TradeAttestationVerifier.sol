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
///
/// @dev    MEDIUM in `docs/phase-3-review.md`: the binding circuit↔verifier
///         is security-critical. `registerVerifier` is therefore a one-shot
///         per class (first-set only). Replacements require the
///         propose/commit flow gated by `CHANGE_DELAY` so an owner-key
///         compromise cannot instantly swap in a malicious verifier.
///         Existing testnet TAVs deployed before this contract are
///         immutable and continue to accept hot-swaps; new deployments
///         (Phase 6 mainnet) use the timelock.
contract TradeAttestationVerifier is ITradeAttestationVerifier, Ownable {
    /// @dev Minimum delay between `proposeVerifierChange` and
    ///      `commitVerifierChange`. Two days lines up with the typical
    ///      Helios upgrade window: long enough for users / auditors to see
    ///      the proposed change, short enough not to strand a circuit fix
    ///      behind an emergency.
    uint256 public constant CHANGE_DELAY = 2 days;

    struct PendingChange {
        address verifier;
        uint64 readyAt;
    }

    mapping(bytes32 => address) public verifierByClassMap;
    mapping(bytes32 => PendingChange) public pendingChanges;

    event VerifierChangeProposed(
        bytes32 indexed declaredClass, address indexed verifier, uint64 readyAt
    );
    event VerifierChangeCancelled(bytes32 indexed declaredClass, address indexed verifier);

    error ZeroAddress();
    error AlreadyRegistered();
    error UseProposeCommit();
    error NoPendingChange();
    error ChangeNotReady();

    constructor(address owner_) Ownable(owner_) { }

    /// @notice First-time registration of a class verifier. Reverts if a
    ///         verifier is already bound — replacements must use
    ///         `proposeVerifierChange` + `commitVerifierChange`.
    function registerVerifier(bytes32 declaredClass, address verifier) external onlyOwner {
        if (verifier == address(0)) revert ZeroAddress();
        if (verifierByClassMap[declaredClass] != address(0)) revert AlreadyRegistered();
        verifierByClassMap[declaredClass] = verifier;
        emit VerifierRegistered(declaredClass, verifier);
    }

    /// @notice Propose a verifier replacement. The change does not take
    ///         effect until `commitVerifierChange` is called after
    ///         `CHANGE_DELAY` has elapsed. A subsequent `propose` call
    ///         overwrites any prior pending change for the same class,
    ///         resetting the timer.
    function proposeVerifierChange(bytes32 declaredClass, address verifier) external onlyOwner {
        if (verifier == address(0)) revert ZeroAddress();
        uint64 readyAt = uint64(block.timestamp + CHANGE_DELAY);
        pendingChanges[declaredClass] = PendingChange({ verifier: verifier, readyAt: readyAt });
        emit VerifierChangeProposed(declaredClass, verifier, readyAt);
    }

    /// @notice Commit a previously-proposed verifier replacement. Reverts
    ///         if no change is pending or the delay has not elapsed.
    function commitVerifierChange(bytes32 declaredClass) external onlyOwner {
        PendingChange storage p = pendingChanges[declaredClass];
        if (p.verifier == address(0)) revert NoPendingChange();
        if (block.timestamp < p.readyAt) revert ChangeNotReady();
        address newVerifier = p.verifier;
        delete pendingChanges[declaredClass];
        verifierByClassMap[declaredClass] = newVerifier;
        emit VerifierRegistered(declaredClass, newVerifier);
    }

    /// @notice Discard a pending verifier change without applying it.
    function cancelVerifierChange(bytes32 declaredClass) external onlyOwner {
        PendingChange storage p = pendingChanges[declaredClass];
        if (p.verifier == address(0)) revert NoPendingChange();
        address cancelled = p.verifier;
        delete pendingChanges[declaredClass];
        emit VerifierChangeCancelled(declaredClass, cancelled);
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
