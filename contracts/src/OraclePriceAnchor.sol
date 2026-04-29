// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Ownable } from "@openzeppelin/contracts/access/Ownable.sol";
import { EIP712 } from "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import { ECDSA } from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";

import { IOracleAnchor } from "./interfaces/IOracleAnchor.sol";

/// @title OraclePriceAnchor
/// @notice Append-only EIP-712 ledger of Poseidon roots produced by the
///         off-chain Helios price oracle. Each commit pins down a window
///         of signed price snapshots; the strategy circuits consume one
///         such root as their public `oracle_root` input.
///
///         Window semantics: `(start, end]` measured in **block.timestamp
///         milliseconds** (oracle internal clock) — both fields are
///         oracle-supplied so the contract is agnostic to wall-clock
///         drift between the chain and the off-chain process.
///
///         A commit is valid iff:
///           1. recovered signer == `oracleSigner`,
///           2. `windowEnd > windowStart` (non-empty),
///           3. `windowStart >= prev.windowEnd` (monotonic, no gaps OK),
///           4. `root != bytes32(0)` (sentinel for "no snapshots").
///
///         The anchor is intentionally immutable — no UUPS proxy. If
///         the signer rotates we deploy a new anchor and update the
///         oracle service config; subgraph indexers track the new
///         address from the deployments JSON.
contract OraclePriceAnchor is IOracleAnchor, Ownable, EIP712 {
    /// @dev Hash of the EIP-712 type used for `commit`. Keep in lockstep
    ///      with `services/oracle/src/oracle/anchor.py`.
    bytes32 public constant COMMIT_TYPEHASH = keccak256(
        "OraclePriceCommit(bytes32 root,uint64 windowStart,uint64 windowEnd,uint256 nonce)"
    );

    address public oracleSigner;
    uint256 public nonce; // strictly-increasing replay guard

    Commit[] internal _commits;
    mapping(bytes32 => bool) internal _seenRoot;

    constructor(address signer_, address owner_)
        Ownable(owner_)
        EIP712("HeliosOraclePriceAnchor", "1")
    {
        if (signer_ == address(0)) revert ZeroAddress();
        oracleSigner = signer_;
    }

    // ── Admin ──────────────────────────────────────────────────────

    function setSigner(address signer_) external onlyOwner {
        if (signer_ == address(0)) revert ZeroAddress();
        emit SignerUpdated(oracleSigner, signer_);
        oracleSigner = signer_;
    }

    // ── Mutating ───────────────────────────────────────────────────

    /// @notice Commit a Poseidon root for one window.
    /// @param root         Poseidon root over the price-snapshot ring.
    /// @param windowStart  Earliest snapshot ts_ms (inclusive).
    /// @param windowEnd    Latest snapshot ts_ms (inclusive); must be > start.
    /// @param sig          EIP-712 signature over (root, windowStart,
    ///                     windowEnd, nonce) by `oracleSigner`.
    function commit(bytes32 root, uint64 windowStart, uint64 windowEnd, bytes calldata sig)
        external
    {
        if (root == bytes32(0)) revert ZeroRoot();
        if (windowEnd <= windowStart) revert EmptyWindow();
        uint256 n = _commits.length;
        if (n != 0 && windowStart < _commits[n - 1].windowEnd) revert NonMonotonicWindow();

        bytes32 structHash =
            keccak256(abi.encode(COMMIT_TYPEHASH, root, windowStart, windowEnd, nonce));
        bytes32 digest = _hashTypedDataV4(structHash);
        address recovered = ECDSA.recover(digest, sig);
        if (recovered != oracleSigner) revert InvalidSigner();

        unchecked {
            ++nonce;
        }

        _commits.push(
            Commit({
                root: root,
                windowStart: windowStart,
                windowEnd: windowEnd,
                committedAt: uint64(block.timestamp),
                signer: recovered
            })
        );
        _seenRoot[root] = true;

        emit Committed(_commits.length - 1, root, windowStart, windowEnd, recovered);
    }

    // ── Views ──────────────────────────────────────────────────────

    function latest() external view returns (Commit memory) {
        uint256 n = _commits.length;
        if (n == 0) revert UnknownIndex();
        return _commits[n - 1];
    }

    function commitCount() external view returns (uint256) {
        return _commits.length;
    }

    function commitAt(uint256 index) external view returns (Commit memory) {
        if (index >= _commits.length) revert UnknownIndex();
        return _commits[index];
    }

    function isKnownRoot(bytes32 root) external view returns (bool) {
        return _seenRoot[root];
    }

    function domainSeparator() external view returns (bytes32) {
        return _domainSeparatorV4();
    }

    function hashCommit(bytes32 root, uint64 windowStart, uint64 windowEnd, uint256 nonce_)
        external
        view
        returns (bytes32)
    {
        bytes32 structHash =
            keccak256(abi.encode(COMMIT_TYPEHASH, root, windowStart, windowEnd, nonce_));
        return _hashTypedDataV4(structHash);
    }
}
