// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Test } from "forge-std/Test.sol";
import { OraclePriceAnchor } from "../src/OraclePriceAnchor.sol";
import { IOracleAnchor } from "../src/interfaces/IOracleAnchor.sol";
import { Ownable } from "@openzeppelin/contracts/access/Ownable.sol";

contract OraclePriceAnchorTest is Test {
    OraclePriceAnchor internal anchor;

    address internal owner = makeAddr("owner");
    uint256 internal signerPk = 0xBEEF;
    address internal signerAddr;
    uint256 internal otherPk = 0xDEAD;

    function setUp() public {
        signerAddr = vm.addr(signerPk);
        anchor = new OraclePriceAnchor(signerAddr, owner);
    }

    // ── Helpers ─────────────────────────────────────────────────────

    function _sign(uint256 pk, bytes32 root, uint64 ws, uint64 we, uint256 nonce_)
        internal
        view
        returns (bytes memory)
    {
        bytes32 digest = anchor.hashCommit(root, ws, we, nonce_);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(pk, digest);
        return abi.encodePacked(r, s, v);
    }

    // ── Constructor ────────────────────────────────────────────────

    function test_constructor_rejectsZeroSigner() public {
        vm.expectRevert(IOracleAnchor.ZeroAddress.selector);
        new OraclePriceAnchor(address(0), owner);
    }

    // ── commit ──────────────────────────────────────────────────────

    function test_commit_storesAndExposes() public {
        bytes32 root = keccak256("root-1");
        uint64 ws = 100;
        uint64 we = 200;
        bytes memory sig = _sign(signerPk, root, ws, we, 0);

        vm.expectEmit(true, true, true, true);
        emit IOracleAnchor.Committed(0, root, ws, we, signerAddr);
        anchor.commit(root, ws, we, sig);

        assertEq(anchor.commitCount(), 1);
        assertTrue(anchor.isKnownRoot(root));
        IOracleAnchor.Commit memory c = anchor.latest();
        assertEq(c.root, root);
        assertEq(c.windowStart, ws);
        assertEq(c.windowEnd, we);
        assertEq(c.signer, signerAddr);
        assertEq(anchor.nonce(), 1);
    }

    function test_commit_rejectsWrongSigner() public {
        bytes32 root = keccak256("r");
        bytes memory sig = _sign(otherPk, root, 100, 200, 0);
        vm.expectRevert(IOracleAnchor.InvalidSigner.selector);
        anchor.commit(root, 100, 200, sig);
    }

    function test_commit_rejectsZeroRoot() public {
        bytes memory sig = _sign(signerPk, bytes32(0), 100, 200, 0);
        vm.expectRevert(IOracleAnchor.ZeroRoot.selector);
        anchor.commit(bytes32(0), 100, 200, sig);
    }

    function test_commit_rejectsEmptyWindow() public {
        bytes32 root = keccak256("r");
        bytes memory sig = _sign(signerPk, root, 200, 200, 0);
        vm.expectRevert(IOracleAnchor.EmptyWindow.selector);
        anchor.commit(root, 200, 200, sig);
    }

    function test_commit_rejectsBackwardWindow() public {
        bytes32 r1 = keccak256("r1");
        anchor.commit(r1, 100, 200, _sign(signerPk, r1, 100, 200, 0));

        bytes32 r2 = keccak256("r2");
        bytes memory sig = _sign(signerPk, r2, 150, 250, 1);
        vm.expectRevert(IOracleAnchor.NonMonotonicWindow.selector);
        anchor.commit(r2, 150, 250, sig);
    }

    function test_commit_acceptsAdjacentWindow() public {
        bytes32 r1 = keccak256("r1");
        anchor.commit(r1, 100, 200, _sign(signerPk, r1, 100, 200, 0));
        bytes32 r2 = keccak256("r2");
        // ws == prev.we is OK (adjacent, no gap, no overlap).
        anchor.commit(r2, 200, 300, _sign(signerPk, r2, 200, 300, 1));
        assertEq(anchor.commitCount(), 2);
    }

    function test_commit_replayedSigRejected() public {
        bytes32 root = keccak256("r");
        uint64 ws = 100;
        uint64 we = 200;
        bytes memory sig = _sign(signerPk, root, ws, we, 0);
        anchor.commit(root, ws, we, sig);
        // Use a forward-monotonic window so the NonMonotonicWindow check
        // passes — the failure must come from the nonce-bumped digest no
        // longer matching the stale signature.
        bytes memory staleSig = _sign(signerPk, root, 300, 400, 0);
        vm.expectRevert(IOracleAnchor.InvalidSigner.selector);
        anchor.commit(root, 300, 400, staleSig);
    }

    function test_commit_unknownIndexReverts() public {
        vm.expectRevert(IOracleAnchor.UnknownIndex.selector);
        anchor.latest();
        vm.expectRevert(IOracleAnchor.UnknownIndex.selector);
        anchor.commitAt(0);
    }

    // ── Admin ──────────────────────────────────────────────────────

    function test_setSigner_onlyOwner() public {
        address newSigner = makeAddr("newSigner");
        vm.expectRevert(abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, address(this)));
        anchor.setSigner(newSigner);

        vm.prank(owner);
        anchor.setSigner(newSigner);
        assertEq(anchor.oracleSigner(), newSigner);
    }

    function test_setSigner_rejectsZero() public {
        vm.prank(owner);
        vm.expectRevert(IOracleAnchor.ZeroAddress.selector);
        anchor.setSigner(address(0));
    }

    function test_signerRotation_letsNewSignerCommit() public {
        uint256 newPk = 0xCAFE;
        address newSigner = vm.addr(newPk);
        vm.prank(owner);
        anchor.setSigner(newSigner);

        bytes32 root = keccak256("r");
        bytes memory oldSig = _sign(signerPk, root, 100, 200, 0);
        vm.expectRevert(IOracleAnchor.InvalidSigner.selector);
        anchor.commit(root, 100, 200, oldSig);

        bytes memory newSig = _sign(newPk, root, 100, 200, 0);
        anchor.commit(root, 100, 200, newSig);
        assertTrue(anchor.isKnownRoot(root));
    }
}
