// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Test } from "forge-std/Test.sol";
import { MomentumV1Verifier } from "../src/verifiers/MomentumV1Verifier.sol";
import { MomentumV1VerifierAdapter } from "../src/verifiers/MomentumV1VerifierAdapter.sol";

/// @notice End-to-end test: real Groth16 proof generated off-chain by
///         circuits/scripts/gen-fixture.js → on-chain verification through
///         MomentumV1Verifier (snarkjs-generated) wrapped by the dynamic-shape
///         adapter that TradeAttestationVerifier dispatches into.
///         The TradeAttestationVerifier integration lands when this branch
///         merges into phase-1.
contract MomentumV1VerifierTest is Test {
    MomentumV1Verifier internal raw;
    MomentumV1VerifierAdapter internal adapter;

    struct Proof {
        uint256[2] a;
        uint256[2][2] b;
        uint256[2] c;
    }

    function setUp() public {
        raw = new MomentumV1Verifier();
        adapter = new MomentumV1VerifierAdapter(address(raw));
    }

    function _loadFixture() internal view returns (Proof memory p, uint256[] memory pubInputs) {
        string memory json = vm.readFile("./test/fixtures/momentum_v1.json");
        p.a[0] = vm.parseJsonUint(json, ".proof.a[0]");
        p.a[1] = vm.parseJsonUint(json, ".proof.a[1]");
        p.b[0][0] = vm.parseJsonUint(json, ".proof.b[0][0]");
        p.b[0][1] = vm.parseJsonUint(json, ".proof.b[0][1]");
        p.b[1][0] = vm.parseJsonUint(json, ".proof.b[1][0]");
        p.b[1][1] = vm.parseJsonUint(json, ".proof.b[1][1]");
        p.c[0] = vm.parseJsonUint(json, ".proof.c[0]");
        p.c[1] = vm.parseJsonUint(json, ".proof.c[1]");
        pubInputs = vm.parseJsonUintArray(json, ".publicSignals");
    }

    function test_RawVerifier_AcceptsRealProof() public view {
        (Proof memory p, uint256[] memory pubInputs) = _loadFixture();
        require(pubInputs.length == 11, "fixture: bad pub input count");
        uint256[11] memory fixedInputs;
        for (uint256 i = 0; i < 11; i++) {
            fixedInputs[i] = pubInputs[i];
        }
        assertTrue(raw.verifyProof(p.a, p.b, p.c, fixedInputs));
    }

    function test_Adapter_AcceptsRealProof() public view {
        (Proof memory p, uint256[] memory pubInputs) = _loadFixture();
        assertTrue(adapter.verifyProof(p.a, p.b, p.c, pubInputs));
    }

    function test_Adapter_RejectsTamperedPublicInput() public {
        (Proof memory p, uint256[] memory pubInputs) = _loadFixture();
        // Bump trade_hash (publicSignals[0]) by 1 → proof should no longer verify.
        pubInputs[0] = pubInputs[0] + 1;
        assertFalse(adapter.verifyProof(p.a, p.b, p.c, pubInputs));
    }

    function test_Adapter_RevertsOnWrongPubInputCount() public {
        (Proof memory p, uint256[] memory pubInputs) = _loadFixture();
        uint256[] memory shortInputs = new uint256[](pubInputs.length - 1);
        for (uint256 i = 0; i < shortInputs.length; i++) {
            shortInputs[i] = pubInputs[i];
        }
        vm.expectRevert(
            abi.encodeWithSelector(
                MomentumV1VerifierAdapter.WrongPublicInputCount.selector, shortInputs.length, 11
            )
        );
        adapter.verifyProof(p.a, p.b, p.c, shortInputs);
    }
}
