// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";

import { ClassIds } from "../src/ClassIds.sol";
import { TradeAttestationVerifier } from "../src/TradeAttestationVerifier.sol";

import { YieldRotationV1Verifier } from "../src/verifiers/YieldRotationV1Verifier.sol";
import {
    YieldRotationV1VerifierAdapter
} from "../src/verifiers/YieldRotationV1VerifierAdapter.sol";

/// @title CompleteCutoverFinish
/// @notice Finishing-touches for `DeployCrossDecimalCutover`. The first
///         broadcast landed 5/10 txs before the Kite RPC dropped the
///         YR-verifier tx and forge hung. This script picks up: it
///         deploys the YR verifier + adapter fresh, then calls
///         `registerVerifier(...)` for all three class IDs on the
///         already-deployed TAV (passed via `NEW_TAV` env). Existing
///         mom/mr adapter addresses come in via env so the same TAV
///         remains the single owner-managed surface.
///
///         Required env:
///           - DEPLOYER_PK              owner of the new TAV
///           - NEW_TAV                  TAV deployed by the first script
///           - NEW_MOM_ADAPTER          momentum adapter (1st broadcast)
///           - NEW_MR_ADAPTER           mean-reversion adapter (1st broadcast)
///         Optional:
///           - OUT_LABEL                deployments/<label>.json target
contract CompleteCutoverFinish is Script {
    bytes32 internal constant CLASS_MOM = ClassIds.MOMENTUM_V1;
    bytes32 internal constant CLASS_MR = ClassIds.MEAN_REVERSION_V1;
    bytes32 internal constant CLASS_YR = ClassIds.YIELD_ROTATION_V1;

    struct Out {
        address yieldRotationVerifier;
        address yieldRotationVerifierAdapter;
    }

    function run() external returns (Out memory a) {
        uint256 pk = vm.envUint("DEPLOYER_PK");
        address newTAV = vm.envAddress("NEW_TAV");
        address newMomAdapter = vm.envAddress("NEW_MOM_ADAPTER");
        address newMrAdapter = vm.envAddress("NEW_MR_ADAPTER");
        string memory label = vm.envOr("OUT_LABEL", _chainName());

        vm.startBroadcast(pk);
        YieldRotationV1Verifier yr = new YieldRotationV1Verifier();
        a.yieldRotationVerifier = address(yr);
        a.yieldRotationVerifierAdapter = address(new YieldRotationV1VerifierAdapter(address(yr)));

        TradeAttestationVerifier tav = TradeAttestationVerifier(newTAV);
        tav.registerVerifier(CLASS_MOM, newMomAdapter);
        tav.registerVerifier(CLASS_MR, newMrAdapter);
        tav.registerVerifier(CLASS_YR, a.yieldRotationVerifierAdapter);
        vm.stopBroadcast();

        console2.log("=== cutover-finish ===");
        console2.log("YR Verifier:        ", a.yieldRotationVerifier);
        console2.log("YR Adapter:         ", a.yieldRotationVerifierAdapter);
        console2.log("Registered MOM on:  ", newTAV);
        _patchJson(string.concat("./deployments/", label, ".json"), a);
    }

    function _patchJson(string memory file, Out memory a) internal {
        _writeAddr(file, ".addresses.yieldRotationVerifier", a.yieldRotationVerifier);
        _writeAddr(file, ".addresses.yieldRotationVerifierAdapter", a.yieldRotationVerifierAdapter);
        console2.log("merged into:", file);
    }

    function _writeAddr(string memory file, string memory path, address v) internal {
        vm.writeJson(string.concat('"', _addrLower(v), '"'), file, path);
    }

    function _addrLower(address v) internal pure returns (string memory) {
        bytes memory hexChars = "0123456789abcdef";
        bytes20 b = bytes20(v);
        bytes memory out = new bytes(42);
        out[0] = "0";
        out[1] = "x";
        for (uint256 i = 0; i < 20; i++) {
            out[2 + i * 2] = hexChars[uint8(b[i] >> 4)];
            out[3 + i * 2] = hexChars[uint8(b[i] & 0x0f)];
        }
        return string(out);
    }

    function _chainName() internal view returns (string memory) {
        if (block.chainid == 2368) return "kite-testnet";
        if (block.chainid == 31_337) return "anvil-kite-phase2";
        return "unknown-chain";
    }
}
