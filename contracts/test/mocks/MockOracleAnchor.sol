// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { IOracleAnchor } from "../../src/interfaces/IOracleAnchor.sol";

/// @notice Minimal mock for `IOracleAnchor` covering only the surface
///         the WS-CX-1 `AllocatorVault.triggerDefund` freshness gate
///         reads: `commitCount()` + `latest().committedAt`. Tests poke
///         `setLatest(committedAt)` to drive the gate.
contract MockOracleAnchor is IOracleAnchor {
    Commit internal _latest;
    uint256 internal _count;

    function setLatest(uint64 committedAt_) external {
        _latest = Commit({
            root: bytes32(uint256(1)),
            windowStart: 0,
            windowEnd: committedAt_,
            committedAt: committedAt_,
            signer: address(this)
        });
        _count = 1;
    }

    function clear() external {
        delete _latest;
        _count = 0;
    }

    function latest() external view returns (Commit memory) {
        if (_count == 0) revert UnknownIndex();
        return _latest;
    }

    function commitCount() external view returns (uint256) {
        return _count;
    }

    function commitAt(uint256) external view returns (Commit memory) {
        if (_count == 0) revert UnknownIndex();
        return _latest;
    }

    function isKnownRoot(bytes32 root) external view returns (bool) {
        return _count != 0 && root == _latest.root;
    }

    function commit(bytes32, uint64, uint64, bytes calldata) external pure {
        revert("mock: use setLatest");
    }

    function setSigner(address) external pure { }

    function revokeRoot(bytes32) external pure { }

    function unrevokeRoot(bytes32) external pure { }

    function freshness(bytes32 root) external view returns (uint64) {
        if (_count == 0 || root != _latest.root) return 0;
        return _latest.committedAt;
    }

    function oracleSigner() external view returns (address) {
        return address(this);
    }

    function nonce() external view returns (uint256) {
        return _count;
    }

    function hashCommit(bytes32, uint64, uint64, uint256) external pure returns (bytes32) {
        return bytes32(0);
    }
}
