// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";

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
import { ReputationAnchorV2 } from "../src/ReputationAnchorV2.sol";

/// @notice Phase-2 upgrade. Replaces Phase-1's mock-Groth16 verifiers
///         with the real per-class adapters and deploys ReputationAnchorV2
///         (fresh address — V1 was non-upgradeable).
///
///         Reads existing infrastructure from env, never mutates Phase-1
///         contracts beyond `TradeAttestationVerifier.registerVerifier`.
///         Note: the existing StrategyRegistry/AllocatorRegistry have V1
///         baked in as `immutable reputationAnchor`, so V2's reputation
///         deltas will *not* propagate back to those registries — they're
///         used here as audit-grade event sources (componentsHash anchored
///         on-chain) until Phase 5 redeploys the registries pointing at V2.
///
///         Required env:
///           - DEPLOYER_PK
///           - TRADE_VERIFIER (address) — Phase-1 TradeAttestationVerifier
///           - STRATEGY_REGISTRY (address)
///           - ALLOCATOR_REGISTRY (address)
///           - REP_SIGNER (address) — V2 anchor's signer (can match V1)
///         Optional env:
///           - REP_OAPP (address) — defaults to 0 if Phase 5 not wired
contract DeployPhase2Upgrade is Script {
    bytes32 internal constant CLASS_MOM = keccak256("momentum_v1");
    bytes32 internal constant CLASS_MR = keccak256("mean_reversion_v1");
    bytes32 internal constant CLASS_YR = keccak256("yield_rotation_v1");

    function run() external {
        uint256 pk = vm.envUint("DEPLOYER_PK");
        address deployer = vm.addr(pk);

        TradeAttestationVerifier tav = TradeAttestationVerifier(vm.envAddress("TRADE_VERIFIER"));
        address strategyRegistry = vm.envAddress("STRATEGY_REGISTRY");
        address allocatorRegistry = vm.envAddress("ALLOCATOR_REGISTRY");
        address repSigner = vm.envAddress("REP_SIGNER");
        address repOApp = vm.envOr("REP_OAPP", address(0));

        vm.startBroadcast(pk);

        // ── Real per-class Groth16 verifiers + adapters ──────────────
        MomentumV1Verifier momRaw = new MomentumV1Verifier();
        MomentumV1VerifierAdapter momAdapter = new MomentumV1VerifierAdapter(address(momRaw));

        MeanReversionV1Verifier mrRaw = new MeanReversionV1Verifier();
        MeanReversionV1VerifierAdapter mrAdapter =
            new MeanReversionV1VerifierAdapter(address(mrRaw));

        YieldRotationV1Verifier yrRaw = new YieldRotationV1Verifier();
        YieldRotationV1VerifierAdapter yrAdapter =
            new YieldRotationV1VerifierAdapter(address(yrRaw));

        // Re-point TradeAttestationVerifier at the new adapters.
        tav.registerVerifier(CLASS_MOM, address(momAdapter));
        tav.registerVerifier(CLASS_MR, address(mrAdapter));
        tav.registerVerifier(CLASS_YR, address(yrAdapter));

        // ── ReputationAnchorV2 ───────────────────────────────────────
        ReputationAnchorV2 anchorV2 = new ReputationAnchorV2(repSigner, repOApp, deployer);
        anchorV2.setRegistries(strategyRegistry, allocatorRegistry);

        vm.stopBroadcast();

        console2.log("=== Helios Phase-2 upgrade ===");
        console2.log("MomentumV1Verifier:        ", address(momRaw));
        console2.log("MomentumV1VerifierAdapter: ", address(momAdapter));
        console2.log("MeanReversionV1Verifier:        ", address(mrRaw));
        console2.log("MeanReversionV1VerifierAdapter: ", address(mrAdapter));
        console2.log("YieldRotationV1Verifier:        ", address(yrRaw));
        console2.log("YieldRotationV1VerifierAdapter: ", address(yrAdapter));
        console2.log("ReputationAnchorV2:        ", address(anchorV2));
        console2.log("(remember to update deployments/<chain>.json)");
    }
}
