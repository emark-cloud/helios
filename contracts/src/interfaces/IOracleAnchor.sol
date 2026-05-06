// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

/// @title IOracleAnchor
/// @notice Shared interface for the Phase-2 oracle anchors (price + yield).
///         Both anchors are append-only ring buffers of EIP-712 signed
///         (root, windowStart, windowEnd) commitments produced by the
///         off-chain Helios oracle. Strategy circuits consume a stored
///         root as their public `oracle_root` / `yield_oracle_root`
///         input — the on-chain anchor is what makes that root binding.
///
///         Helios.md §10 (oracle), §9 (circuit public inputs).
interface IOracleAnchor {
    /// @notice One committed snapshot of the off-chain Poseidon ring root.
    /// @dev Stored as a Poseidon BN254 field element in the high-order
    ///      bytes of `bytes32` (left-padded). Circuits consume this as a
    ///      uint254 directly; on-chain readers should treat it opaquely.
    struct Commit {
        bytes32 root; // Poseidon root over the snapshot ring
        uint64 windowStart; // first block / ts_ms covered (inclusive)
        uint64 windowEnd; // last block / ts_ms covered (inclusive)
        uint64 committedAt; // block.timestamp at write
        address signer; // recovered EIP-712 signer (audit only)
    }

    event SignerUpdated(address indexed previous, address indexed next);
    event Committed(
        uint256 indexed index,
        bytes32 indexed root,
        uint64 windowStart,
        uint64 windowEnd,
        address indexed signer
    );
    event RootRevoked(bytes32 indexed root);
    event RootUnrevoked(bytes32 indexed root);

    error ZeroAddress();
    error ZeroRoot();
    error InvalidSigner();
    error EmptyWindow();
    error NonMonotonicWindow();
    error UnknownIndex();
    error UnknownRoot();
    error RootNotRevoked();

    /// @notice Latest commit.
    /// @dev Reverts with `UnknownIndex` if no commits exist yet.
    function latest() external view returns (Commit memory);

    /// @notice Number of commits ever made (monotonic).
    function commitCount() external view returns (uint256);

    /// @notice Read a specific commit by index. Index 0 = first ever.
    function commitAt(uint256 index) external view returns (Commit memory);

    /// @notice Whether the given root has been committed by this anchor.
    /// @dev O(1) lookup; intended for circuits / verifiers that want a
    ///      cheap "has the oracle ever attested this root" check.
    function isKnownRoot(bytes32 root) external view returns (bool);

    /// @notice Commit a root for one window.
    /// @dev Concrete contracts (OraclePriceAnchor / OracleYieldAnchor)
    ///      implement this with anchor-specific EIP-712 type-hashes — a
    ///      price-domain signature cannot be replayed against a yield
    ///      anchor and vice versa.
    function commit(bytes32 root, uint64 windowStart, uint64 windowEnd, bytes calldata sig) external;

    /// @notice Rotate the authorized signer. Owner-gated.
    function setSigner(address signer_) external;

    /// @notice Mark a previously-committed root as no longer valid.
    /// @dev Owner-gated. Used when a signer rotation under suspicion of
    ///      compromise leaves attested roots that should not back future
    ///      proofs. The commit ledger is preserved (append-only) — only
    ///      the `isKnownRoot` lookup flips to `false`. Reverts with
    ///      `UnknownRoot` if the root was never committed (or already
    ///      revoked) so callers can detect typos.
    function revokeRoot(bytes32 root) external;

    /// @notice Reverse a `revokeRoot`, restoring the root's `isKnownRoot`
    ///         status. Owner-gated (HIGH #9 in `docs/phase-3-review.md`).
    ///         Reverts with `UnknownRoot` if the root was never committed
    ///         and `RootNotRevoked` if it's still active. Without this
    ///         pair, a misclick on `revokeRoot` permanently bricks every
    ///         strategy whose proofs reference the targeted root.
    function unrevokeRoot(bytes32 root) external;

    /// @notice `committedAt` timestamp for a root, or 0 if never committed
    ///         or currently revoked. Lets consumers (StrategyVault) gate
    ///         on max-staleness without scanning the commit array — HIGH
    ///         #6 in `docs/phase-3-review.md`. Equivalent to
    ///         `isKnownRoot(root) ? <committedAt> : 0`.
    function freshness(bytes32 root) external view returns (uint64);

    /// @notice Address authorized to sign commits.
    function oracleSigner() external view returns (address);

    /// @notice Strictly-increasing replay nonce, included in the EIP-712 digest.
    function nonce() external view returns (uint256);

    /// @notice EIP-712 digest the signer is expected to produce, given
    ///         the current `nonce()` (or any historical/future value).
    function hashCommit(bytes32 root, uint64 windowStart, uint64 windowEnd, uint256 nonce_)
        external
        view
        returns (bytes32);
}
