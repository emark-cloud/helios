// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";

import { ClassIds } from "../src/ClassIds.sol";
import { TradeAttestationVerifier } from "../src/TradeAttestationVerifier.sol";

import { MomentumV1Verifier } from "../src/verifiers/MomentumV1Verifier.sol";
import { MeanReversionV1Verifier } from "../src/verifiers/MeanReversionV1Verifier.sol";
import { MomentumV1VerifierAdapter } from "../src/verifiers/MomentumV1VerifierAdapter.sol";
import {
    MeanReversionV1VerifierAdapter
} from "../src/verifiers/MeanReversionV1VerifierAdapter.sol";

/// @title ProposeVerifierRotation
/// @notice Deploys regenerated `momentum_v1` + `mean_reversion_v1`
///         verifiers (with the new Constraint 0 zero-amount reject)
///         and proposes the TAV class-map rotation. The commit must
///         follow ≥ 2 days later via `CommitVerifierRotation`
///         (`TradeAttestationVerifier.CHANGE_DELAY = 2 days`).
///
///         `yield_rotation_v1` is intentionally NOT touched — its
///         Constraint 7 already enforces the equivalent positivity
///         check, so the circuit + verifier address are unchanged.
///
///         Required env:
///           - DEPLOYER_PK    funded testnet key (TAV owner)
///           - TRADE_VERIFIER existing TAV address (owner == deployer)
contract ProposeVerifierRotation is Script {
    bytes32 internal constant CLASS_MOM = ClassIds.MOMENTUM_V1;
    bytes32 internal constant CLASS_MR = ClassIds.MEAN_REVERSION_V1;

    struct Pending {
        address momentumVerifier;
        address momentumVerifierAdapter;
        address meanReversionVerifier;
        address meanReversionVerifierAdapter;
        uint256 commitEta;
    }

    function run() external returns (Pending memory p) {
        uint256 pk = vm.envUint("DEPLOYER_PK");
        TradeAttestationVerifier tav = TradeAttestationVerifier(vm.envAddress("TRADE_VERIFIER"));

        vm.startBroadcast(pk);

        MomentumV1Verifier mom = new MomentumV1Verifier();
        p.momentumVerifier = address(mom);
        p.momentumVerifierAdapter = address(new MomentumV1VerifierAdapter(address(mom)));

        MeanReversionV1Verifier mr = new MeanReversionV1Verifier();
        p.meanReversionVerifier = address(mr);
        p.meanReversionVerifierAdapter = address(new MeanReversionV1VerifierAdapter(address(mr)));

        tav.proposeVerifierChange(CLASS_MOM, p.momentumVerifierAdapter);
        tav.proposeVerifierChange(CLASS_MR, p.meanReversionVerifierAdapter);

        vm.stopBroadcast();

        p.commitEta = block.timestamp + tav.CHANGE_DELAY();

        _log(p);
    }

    function _log(Pending memory p) internal view {
        console2.log("=== verifier-rotation propose ===");
        console2.log("chainId:                        ", block.chainid);
        console2.log("MomentumV1Verifier (new):       ", p.momentumVerifier);
        console2.log("MomentumV1VerifierAdapter (new):", p.momentumVerifierAdapter);
        console2.log("MeanReversionV1Verifier (new):  ", p.meanReversionVerifier);
        console2.log("MeanReversionV1VerifierAdapter: ", p.meanReversionVerifierAdapter);
        console2.log("commit eta (unix):              ", p.commitEta);
        console2.log("Run CommitVerifierRotation after that timestamp.");
    }
}
