// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Test } from "forge-std/Test.sol";
import { YieldRotationV1Verifier } from "../src/verifiers/YieldRotationV1Verifier.sol";
import {
    YieldRotationV1VerifierAdapter
} from "../src/verifiers/YieldRotationV1VerifierAdapter.sol";

/// @notice End-to-end test: real Groth16 proof generated off-chain by
///         circuits/scripts/gen-fixture-yr.js → on-chain verification
///         through YieldRotationV1Verifier (snarkjs-generated) wrapped by
///         the dynamic-shape adapter. YR uses 12 public inputs (rotation
///         layout — see Helios.md §6/§12 and the circuit test).
contract YieldRotationV1VerifierTest is Test {
    YieldRotationV1Verifier internal raw;
    YieldRotationV1VerifierAdapter internal adapter;

    struct Proof {
        uint256[2] a;
        uint256[2][2] b;
        uint256[2] c;
    }

    function setUp() public {
        raw = new YieldRotationV1Verifier();
        adapter = new YieldRotationV1VerifierAdapter(address(raw));
    }

    function _loadFixture() internal view returns (Proof memory p, uint256[] memory pubInputs) {
        string memory json = vm.readFile("./test/fixtures/yield_rotation_v1.json");
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
        require(pubInputs.length == 13, "fixture: bad pub input count");
        uint256[13] memory fixedInputs;
        for (uint256 i = 0; i < 13; i++) {
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
                YieldRotationV1VerifierAdapter.WrongPublicInputCount.selector,
                shortInputs.length,
                13
            )
        );
        adapter.verifyProof(p.a, p.b, p.c, shortInputs);
    }
}
