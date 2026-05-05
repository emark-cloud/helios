// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Ownable } from "@openzeppelin/contracts/access/Ownable.sol";
import { EIP712 } from "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import { ECDSA } from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";

import { IOracleAnchor } from "./interfaces/IOracleAnchor.sol";

/// @title OracleYieldAnchor
/// @notice Sibling of `OraclePriceAnchor` for APY snapshots. The schema
///         and lifecycle are identical — but the two anchors are kept
///         distinct because (a) the yield-rotation circuit consumes a
///         different root from the directional circuits, and (b) the
///         signer-rotation cadence is expected to diverge once Phase 5
///         wires real Aave/Compound feeds (price stays oracle-internal,
///         yield grows external dependencies).
///
///         Per-anchor type-hashes prevent a price commit from being
///         replayed as a yield commit and vice versa.
contract OracleYieldAnchor is IOracleAnchor, Ownable, EIP712 {
    bytes32 public constant COMMIT_TYPEHASH = keccak256(
        "OracleYieldCommit(bytes32 root,uint64 windowStart,uint64 windowEnd,uint256 nonce)"
    );

    address public oracleSigner;
    uint256 public nonce;

    Commit[] internal _commits;
    mapping(bytes32 => bool) internal _seenRoot;

    constructor(address signer_, address owner_)
        Ownable(owner_)
        EIP712("HeliosOracleYieldAnchor", "1")
    {
        if (signer_ == address(0)) revert ZeroAddress();
        oracleSigner = signer_;
    }

    function setSigner(address signer_) external onlyOwner {
        if (signer_ == address(0)) revert ZeroAddress();
        emit SignerUpdated(oracleSigner, signer_);
        oracleSigner = signer_;
    }

    /// @inheritdoc IOracleAnchor
    function revokeRoot(bytes32 root) external onlyOwner {
        if (!_seenRoot[root]) revert UnknownRoot();
        _seenRoot[root] = false;
        emit RootRevoked(root);
    }

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
