// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Test } from "forge-std/Test.sol";
import { TradeAttestationVerifier } from "../src/TradeAttestationVerifier.sol";
import { ITradeAttestationVerifier } from "../src/interfaces/ITradeAttestationVerifier.sol";
import { MockGroth16Verifier } from "./mocks/MockGroth16Verifier.sol";
import { Ownable } from "@openzeppelin/contracts/access/Ownable.sol";

contract TradeAttestationVerifierTest is Test {
    TradeAttestationVerifier internal v;
    MockGroth16Verifier internal momVerifier;
    MockGroth16Verifier internal meanRevVerifier;

    address internal owner = makeAddr("owner");
    address internal randomCaller = makeAddr("rando");

    bytes32 internal constant CLASS_MOMENTUM = keccak256("momentum_v1");
    bytes32 internal constant CLASS_MEAN_REV = keccak256("mean_reversion_v1");

    function setUp() public {
        v = new TradeAttestationVerifier(owner);
        momVerifier = new MockGroth16Verifier(true);
        meanRevVerifier = new MockGroth16Verifier(false);
    }

    function _proof() internal pure returns (bytes memory) {
        uint256[2] memory a = [uint256(1), 2];
        uint256[2][2] memory b = [[uint256(3), 4], [uint256(5), 6]];
        uint256[2] memory c = [uint256(7), 8];
        return abi.encode(a, b, c);
    }

    function _inputs() internal pure returns (uint256[] memory out) {
        out = new uint256[](3);
        out[0] = 11;
        out[1] = 22;
        out[2] = 33;
    }

    function test_RegisterVerifier_OwnerOnly() public {
        vm.expectEmit(true, false, false, true);
        emit ITradeAttestationVerifier.VerifierRegistered(CLASS_MOMENTUM, address(momVerifier));
        vm.prank(owner);
        v.registerVerifier(CLASS_MOMENTUM, address(momVerifier));

        assertEq(v.verifierOf(CLASS_MOMENTUM), address(momVerifier));
    }

    function test_RegisterVerifier_RevertsIfNotOwner() public {
        vm.prank(randomCaller);
        vm.expectRevert(
            abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, randomCaller)
        );
        v.registerVerifier(CLASS_MOMENTUM, address(momVerifier));
    }

    function test_RegisterVerifier_RevertsOnZeroAddress() public {
        vm.prank(owner);
        vm.expectRevert(TradeAttestationVerifier.ZeroAddress.selector);
        v.registerVerifier(CLASS_MOMENTUM, address(0));
    }

    function test_RegisterVerifier_OverwritesExisting() public {
        vm.prank(owner);
        v.registerVerifier(CLASS_MOMENTUM, address(momVerifier));
        vm.prank(owner);
        v.registerVerifier(CLASS_MOMENTUM, address(meanRevVerifier));
        assertEq(v.verifierOf(CLASS_MOMENTUM), address(meanRevVerifier));
    }

    function test_Verify_DispatchesToCorrectClass() public {
        vm.prank(owner);
        v.registerVerifier(CLASS_MOMENTUM, address(momVerifier));
        vm.prank(owner);
        v.registerVerifier(CLASS_MEAN_REV, address(meanRevVerifier));

        // momVerifier.answer == true
        assertTrue(v.verify(CLASS_MOMENTUM, _proof(), _inputs()));
        // meanRevVerifier.answer == false
        assertFalse(v.verify(CLASS_MEAN_REV, _proof(), _inputs()));
    }

    function test_Verify_RevertsOnUnknownClass() public {
        vm.expectRevert(ITradeAttestationVerifier.UnknownClass.selector);
        v.verify(CLASS_MOMENTUM, _proof(), _inputs());
    }

    function test_Verify_RevertsOnBadProofLength() public {
        vm.prank(owner);
        v.registerVerifier(CLASS_MOMENTUM, address(momVerifier));
        bytes memory shortProof = abi.encodePacked(uint256(1), uint256(2));
        vm.expectRevert("TradeAttestationVerifier: bad proof length");
        v.verify(CLASS_MOMENTUM, shortProof, _inputs());
    }

    function test_Verify_AnswerFlipPropagates() public {
        vm.prank(owner);
        v.registerVerifier(CLASS_MOMENTUM, address(momVerifier));
        assertTrue(v.verify(CLASS_MOMENTUM, _proof(), _inputs()));

        momVerifier.setAnswer(false);
        assertFalse(v.verify(CLASS_MOMENTUM, _proof(), _inputs()));
    }
}
