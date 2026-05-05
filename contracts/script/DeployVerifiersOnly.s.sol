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

/// @title DeployVerifiersOnly
/// @notice Minimal companion to `DeployPhase2.s.sol` that redeploys ONLY
///         the per-class Groth16 verifiers + adapters and rotates the
///         existing `TradeAttestationVerifier` class map to the new
///         adapters. Anchors (`ReputationAnchorV2`, `OraclePriceAnchor`,
///         `OracleYieldAnchor`) and registries are intentionally NOT
///         touched — running `DeployPhase2` would orphan them and force
///         every off-chain service to be reconfigured.
///
///         Use case: phase2-followup priority-2 regenerated the circuit
///         VKs (`64580f8` range checks, `6b8dee6` YR block_window_start
///         PI). The verifier `.sol` files now embed different VKs from
///         what's deployed on Kite testnet, so real proofs from the
///         current Python SDK don't verify on-chain. This script flips
///         that one piece without disturbing the rest of the surface.
///
///         Required env:
///           - DEPLOYER_PK    funded testnet key
///           - TRADE_VERIFIER existing TAV address (owner == deployer)
///         Optional:
///           - OUT_LABEL      deployments/<label>.json target (defaults
///                            to chain name, e.g. `kite-testnet`)
contract DeployVerifiersOnly is Script {
    bytes32 internal constant CLASS_MOM = ClassIds.MOMENTUM_V1;
    bytes32 internal constant CLASS_MR = ClassIds.MEAN_REVERSION_V1;
    bytes32 internal constant CLASS_YR = ClassIds.YIELD_ROTATION_V1;

    struct Out {
        address momentumVerifier;
        address momentumVerifierAdapter;
        address meanReversionVerifier;
        address meanReversionVerifierAdapter;
        address yieldRotationVerifier;
        address yieldRotationVerifierAdapter;
    }

    function run() external returns (Out memory a) {
        uint256 pk = vm.envUint("DEPLOYER_PK");
        TradeAttestationVerifier tav = TradeAttestationVerifier(vm.envAddress("TRADE_VERIFIER"));
        string memory label = vm.envOr("OUT_LABEL", _chainName());

        vm.startBroadcast(pk);
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
        a.yieldRotationVerifierAdapter =
            address(new YieldRotationV1VerifierAdapter(address(yr)));
    }

    /// @dev Replace just the six verifier-related address values in the
    ///      existing JSON via `vm.writeJson`. All six keys already exist
    ///      in `kite-testnet.json` (Phase-1 + Phase-2 deploy populated
    ///      them), so writeJson can target each one without needing to
    ///      create new keys. Top-level metadata (`phase2BVariant3DeployedAt`,
    ///      etc.) is preserved verbatim — we only mutate the leaf
    ///      address strings.
    function _patchJson(string memory file, Out memory a) internal {
        _writeAddr(file, ".addresses.momentumVerifier", a.momentumVerifier);
        _writeAddr(file, ".addresses.meanReversionVerifier", a.meanReversionVerifier);
        _writeAddr(file, ".addresses.yieldRotationVerifier", a.yieldRotationVerifier);
        _writeAddr(file, ".addresses.momentumVerifierAdapter", a.momentumVerifierAdapter);
        _writeAddr(file, ".addresses.meanReversionVerifierAdapter", a.meanReversionVerifierAdapter);
        _writeAddr(file, ".addresses.yieldRotationVerifierAdapter", a.yieldRotationVerifierAdapter);
        console2.log("merged into:", file);
    }

    function _writeAddr(string memory file, string memory path, address v) internal {
        // `writeJson` expects the value as a JSON string; we hand it the
        // already-quoted, lowercase address.
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
        console2.log("=== verifiers-only redeploy ===");
        console2.log("chainId:                        ", block.chainid);
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
