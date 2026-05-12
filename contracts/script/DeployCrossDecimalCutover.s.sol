// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";

import { ClassIds } from "../src/ClassIds.sol";
import { TradeAttestationVerifier } from "../src/TradeAttestationVerifier.sol";

import { MomentumV1Verifier } from "../src/verifiers/MomentumV1Verifier.sol";
import { MeanReversionV1Verifier } from "../src/verifiers/MeanReversionV1Verifier.sol";
import { YieldRotationV1Verifier } from "../src/verifiers/YieldRotationV1Verifier.sol";
import { MomentumV1VerifierAdapter } from "../src/verifiers/MomentumV1VerifierAdapter.sol";
import {
    MeanReversionV1VerifierAdapter
} from "../src/verifiers/MeanReversionV1VerifierAdapter.sol";
import {
    YieldRotationV1VerifierAdapter
} from "../src/verifiers/YieldRotationV1VerifierAdapter.sol";

/// @title DeployCrossDecimalCutover
/// @notice Phase-6 cross-decimal slippage cutover. Deploys a FRESH
///         `TradeAttestationVerifier` (compiled from a source where
///         `CHANGE_DELAY = 0`) plus the new 16-PI verifiers + adapters
///         for momentum_v1 / mean_reversion_v1 / yield_rotation_v1, and
///         first-time-registers all three on the new TAV. Companion
///         upgrade flow (`migrateVerifier` on each of the 9 strategy
///         vaults) follows in a separate transaction batch.
///
///         The live TAV at `0x3698F60a…` has `CHANGE_DELAY = 2 days`
///         baked in as a `constant`, so "drop delay, swap, restore"
///         isn't possible in place — a fresh TAV is the structurally
///         clean cutover path.
///
///         Required env:
///           - DEPLOYER_PK    funded testnet key (owner of the new TAV)
///         Optional:
///           - OUT_LABEL      deployments/<label>.json target (defaults
///                            to chain name, e.g. `kite-testnet`)
contract DeployCrossDecimalCutover is Script {
    bytes32 internal constant CLASS_MOM = ClassIds.MOMENTUM_V1;
    bytes32 internal constant CLASS_MR = ClassIds.MEAN_REVERSION_V1;
    bytes32 internal constant CLASS_YR = ClassIds.YIELD_ROTATION_V1;

    struct Out {
        address tradeAttestationVerifier;
        address momentumVerifier;
        address momentumVerifierAdapter;
        address meanReversionVerifier;
        address meanReversionVerifierAdapter;
        address yieldRotationVerifier;
        address yieldRotationVerifierAdapter;
    }

    function run() external returns (Out memory a) {
        uint256 pk = vm.envUint("DEPLOYER_PK");
        address deployer = vm.addr(pk);
        string memory label = vm.envOr("OUT_LABEL", _chainName());

        vm.startBroadcast(pk);
        // Fresh TAV with CHANGE_DELAY=0 (source-coded; no on-chain
        // setter exists for the constant).
        TradeAttestationVerifier tav = new TradeAttestationVerifier(deployer);
        a.tradeAttestationVerifier = address(tav);

        _deploy(a);
        tav.registerVerifier(CLASS_MOM, a.momentumVerifierAdapter);
        tav.registerVerifier(CLASS_MR, a.meanReversionVerifierAdapter);
        tav.registerVerifier(CLASS_YR, a.yieldRotationVerifierAdapter);
        vm.stopBroadcast();

        _log(a);
        _patchJson(string.concat("./deployments/", label, ".json"), a);
    }

    function _deploy(Out memory a) internal {
        MomentumV1Verifier mom = new MomentumV1Verifier();
        a.momentumVerifier = address(mom);
        a.momentumVerifierAdapter = address(new MomentumV1VerifierAdapter(address(mom)));

        MeanReversionV1Verifier mr = new MeanReversionV1Verifier();
        a.meanReversionVerifier = address(mr);
        a.meanReversionVerifierAdapter = address(new MeanReversionV1VerifierAdapter(address(mr)));

        YieldRotationV1Verifier yr = new YieldRotationV1Verifier();
        a.yieldRotationVerifier = address(yr);
        a.yieldRotationVerifierAdapter = address(new YieldRotationV1VerifierAdapter(address(yr)));
    }

    function _patchJson(string memory file, Out memory a) internal {
        _writeAddr(file, ".addresses.tradeAttestationVerifierV2", a.tradeAttestationVerifier);
        _writeAddr(file, ".addresses.momentumVerifier", a.momentumVerifier);
        _writeAddr(file, ".addresses.meanReversionVerifier", a.meanReversionVerifier);
        _writeAddr(file, ".addresses.yieldRotationVerifier", a.yieldRotationVerifier);
        _writeAddr(file, ".addresses.momentumVerifierAdapter", a.momentumVerifierAdapter);
        _writeAddr(file, ".addresses.meanReversionVerifierAdapter", a.meanReversionVerifierAdapter);
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

    function _log(Out memory a) internal view {
        console2.log("=== cross-decimal cutover (Phase-6) ===");
        console2.log("chainId:                        ", block.chainid);
        console2.log("TradeAttestationVerifier (v2):  ", a.tradeAttestationVerifier);
        console2.log("MomentumV1Verifier:             ", a.momentumVerifier);
        console2.log("MomentumV1VerifierAdapter:      ", a.momentumVerifierAdapter);
        console2.log("MeanReversionV1Verifier:        ", a.meanReversionVerifier);
        console2.log("MeanReversionV1VerifierAdapter: ", a.meanReversionVerifierAdapter);
        console2.log("YieldRotationV1Verifier:        ", a.yieldRotationVerifier);
        console2.log("YieldRotationV1VerifierAdapter: ", a.yieldRotationVerifierAdapter);
    }

    function _chainName() internal view returns (string memory) {
        if (block.chainid == 2368) return "kite-testnet";
        if (block.chainid == 84_532) return "base-sepolia";
        if (block.chainid == 421_614) return "arbitrum-sepolia";
        if (block.chainid == 31_337) return "anvil-kite-phase2";
        return "unknown-chain";
    }
}
