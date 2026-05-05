// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Test } from "forge-std/Test.sol";
import { OraclePriceAnchor } from "../src/OraclePriceAnchor.sol";
import { OracleYieldAnchor } from "../src/OracleYieldAnchor.sol";
import { IOracleAnchor } from "../src/interfaces/IOracleAnchor.sol";
import { Ownable } from "@openzeppelin/contracts/access/Ownable.sol";

contract OracleYieldAnchorTest is Test {
    OracleYieldAnchor internal anchor;
    OraclePriceAnchor internal priceAnchor; // for cross-domain replay test

    address internal owner = makeAddr("owner");
    uint256 internal signerPk = 0xBEEF;
    address internal signerAddr;

    function setUp() public {
        signerAddr = vm.addr(signerPk);
        anchor = new OracleYieldAnchor(signerAddr, owner);
        priceAnchor = new OraclePriceAnchor(signerAddr, owner);
    }

    function _signYield(bytes32 root, uint64 ws, uint64 we, uint256 nonce_)
        internal
        view
        returns (bytes memory)
    {
        bytes32 digest = anchor.hashCommit(root, ws, we, nonce_);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(signerPk, digest);
        return abi.encodePacked(r, s, v);
    }

    function _signPrice(bytes32 root, uint64 ws, uint64 we, uint256 nonce_)
        internal
        view
        returns (bytes memory)
    {
        bytes32 digest = priceAnchor.hashCommit(root, ws, we, nonce_);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(signerPk, digest);
        return abi.encodePacked(r, s, v);
    }

    function test_commit_storesAndExposes() public {
        bytes32 root = keccak256("yield-1");
        bytes memory sig = _signYield(root, 100, 200, 0);
        anchor.commit(root, 100, 200, sig);
        assertTrue(anchor.isKnownRoot(root));
        IOracleAnchor.Commit memory c = anchor.latest();
        assertEq(c.root, root);
        assertEq(c.signer, signerAddr);
    }

    function test_priceSig_cannotBeReplayedAsYield() public {
        // Signer signs an OraclePriceCommit; replaying the same bytes as
        // an OracleYieldCommit must fail because the type-hash differs.
        bytes32 root = keccak256("xroot");
        bytes memory priceSig = _signPrice(root, 100, 200, 0);
        vm.expectRevert(IOracleAnchor.InvalidSigner.selector);
        anchor.commit(root, 100, 200, priceSig);
    }

    function test_distinctTypehashes() public view {
        // Sanity: the two anchors hash the same fields to different digests.
        bytes32 root = keccak256("r");
        assertTrue(
            priceAnchor.hashCommit(root, 1, 2, 0) != anchor.hashCommit(root, 1, 2, 0),
            "anchors must produce distinct EIP-712 digests"
        );
    }

    function test_commit_monotonicEnforced() public {
        bytes32 r1 = keccak256("r1");
        anchor.commit(r1, 100, 200, _signYield(r1, 100, 200, 0));
        bytes32 r2 = keccak256("r2");
        // Pre-compute the sig: `vm.expectRevert` only catches the next
        // external call, so the view-call inside `_signYield` would
        // consume it if we computed inline.
        bytes memory sig = _signYield(r2, 150, 250, 1);
        vm.expectRevert(IOracleAnchor.NonMonotonicWindow.selector);
        anchor.commit(r2, 150, 250, sig);
    }

    // ── revokeRoot ─────────────────────────────────────────────────

    function test_revokeRoot_flipsIsKnownRoot() public {
        bytes32 root = keccak256("victim");
        anchor.commit(root, 100, 200, _signYield(root, 100, 200, 0));
        assertTrue(anchor.isKnownRoot(root));

        vm.expectEmit(true, false, false, false);
        emit IOracleAnchor.RootRevoked(root);
        vm.prank(owner);
        anchor.revokeRoot(root);

        assertFalse(anchor.isKnownRoot(root));
        assertEq(anchor.commitCount(), 1);
    }

    function test_revokeRoot_onlyOwner() public {
        bytes32 root = keccak256("r");
        anchor.commit(root, 100, 200, _signYield(root, 100, 200, 0));

        vm.expectRevert(
            abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, address(this))
        );
        anchor.revokeRoot(root);
    }

    function test_revokeRoot_rejectsUnknown() public {
        vm.prank(owner);
        vm.expectRevert(IOracleAnchor.UnknownRoot.selector);
        anchor.revokeRoot(keccak256("never-committed"));
    }
}
