// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";

import { ClassIds } from "../src/ClassIds.sol";
import { StrategyVault } from "../src/StrategyVault.sol";
import { TradeAttestationVerifier } from "../src/TradeAttestationVerifier.sol";

import { MomentumV1Verifier } from "../src/verifiers/MomentumV1Verifier.sol";
import { MeanReversionV1Verifier } from "../src/verifiers/MeanReversionV1Verifier.sol";
import { MomentumV1VerifierAdapter } from "../src/verifiers/MomentumV1VerifierAdapter.sol";
import {
    MeanReversionV1VerifierAdapter
} from "../src/verifiers/MeanReversionV1VerifierAdapter.sol";

interface IUUPS {
    function upgradeToAndCall(address newImplementation, bytes memory data) external;
}

/// @title RedeployTAVAndMigrate
/// @notice Phase 6 #13 chain-side fix. The deployed Kite testnet TAV
///         pre-dates PR #70's `proposeVerifierChange` machinery and has
///         no in-place rotation path (`registerVerifier` is first-set-only).
///         We redeploy a fresh TAV with the timelock code, register the
///         three class adapters cleanly, deploy a new StrategyVault impl
///         with `migrateVerifier(address) reinitializer(2)`, and
///         UUPS-upgrade every strategy-vault proxy with `upgradeToAndCall`
///         that re-points it at the new TAV in a single tx.
///
///         `yield_rotation_v1` reuses the existing adapter — its circuit
///         already has Constraint 7 (`amount_rotating > 0`); only the TAV
///         binding changes, not the YR verifier itself.
///
///         Required env:
///           - DEPLOYER_PK                       owner of every proxy + new TAV
///           - PRICE_ANCHOR                      current OraclePriceAnchor
///           - YIELD_ANCHOR                      current OracleYieldAnchor
///           - YIELD_ROTATION_VERIFIER_ADAPTER   existing YR adapter on testnet
///         Optional:
///           - PROXIES                           comma-separated 9 proxies
///                                                 (defaults to current
///                                                 kite-testnet base + V2 + V3)
///           - OUT_LABEL                         deployments/<label>.json target
contract RedeployTAVAndMigrate is Script {
    bytes32 internal constant CLASS_MOM = ClassIds.MOMENTUM_V1;
    bytes32 internal constant CLASS_MR = ClassIds.MEAN_REVERSION_V1;
    bytes32 internal constant CLASS_YR = ClassIds.YIELD_ROTATION_V1;

    /// @dev Current Kite testnet strategy-vault proxies (post 2026-05-08
    ///      base-trio fresh redeploy + Phase 4 variants). Override via
    ///      `PROXIES` env if running against a different deployment.
    address[9] internal _DEFAULT_PROXIES = [
        0xf11D55a3057A3Da51c9ED63BdC6aE8F666Fa426A, // momentum base
        0xc1B19Df0003eaDF29313826DC874c769Ebb09109, // momentum V2
        0x4e19e5EeC25fc15FBC30A9446d283f4EBeD6462C, // momentum V3
        0xE85FC70edC752D3ff283F3FFFA17598d32b5FC07, // mean-rev base
        0xD4898262Bb6FfBaF5F0C016663a2C59767DDb65F, // mean-rev V2
        0x50c1DCC21E571c106eEE21f42f22FB6eA0d4a708, // mean-rev V3
        0xb7496bE712Ed62fB02c6b9665F74eE6ff136d0d7, // yield base
        0x5605B2E1883428680266fD25cb7429f2001c0c17, // yield V2
        0x3863f44FE693764562c0d239e05C5F194544B0B4 // yield V3
    ];

    struct Out {
        address newTAV;
        address newMomentumVerifier;
        address newMomentumAdapter;
        address newMeanReversionVerifier;
        address newMeanReversionAdapter;
        address yieldRotationAdapter; // unchanged; logged for the deployments-JSON write
        address newStrategyVaultImpl;
    }

    function run() external returns (Out memory a) {
        uint256 pk = vm.envUint("DEPLOYER_PK");
        address deployer = vm.addr(pk);
        address priceAnchor = vm.envAddress("PRICE_ANCHOR");
        address yieldAnchor = vm.envAddress("YIELD_ANCHOR");
        a.yieldRotationAdapter = vm.envAddress("YIELD_ROTATION_VERIFIER_ADAPTER");
        string memory label = vm.envOr("OUT_LABEL", _chainName());
        address[] memory proxies = _proxies();

        vm.startBroadcast(pk);

        // 1. New TAV with timelock code (PR #70 source).
        a.newTAV = address(new TradeAttestationVerifier(deployer));

        // 2. New momentum + mean-reversion verifier+adapter (regenerated
        //    from the post-Constraint-0 circuits).
        a.newMomentumVerifier = address(new MomentumV1Verifier());
        a.newMomentumAdapter = address(new MomentumV1VerifierAdapter(a.newMomentumVerifier));

        a.newMeanReversionVerifier = address(new MeanReversionV1Verifier());
        a.newMeanReversionAdapter =
            address(new MeanReversionV1VerifierAdapter(a.newMeanReversionVerifier));

        // 3. Register all three classes in the new TAV (slots empty —
        //    `registerVerifier` succeeds first time).
        TradeAttestationVerifier newTAV = TradeAttestationVerifier(a.newTAV);
        newTAV.registerVerifier(CLASS_MOM, a.newMomentumAdapter);
        newTAV.registerVerifier(CLASS_MR, a.newMeanReversionAdapter);
        newTAV.registerVerifier(CLASS_YR, a.yieldRotationAdapter);

        // 4. New StrategyVault impl with `migrateVerifier(address)
        //    reinitializer(2)`. Anchors match current testnet.
        a.newStrategyVaultImpl = address(new StrategyVault(priceAnchor, yieldAnchor));

        // 5. UUPS-upgrade each proxy and migrate verifier in a single tx.
        bytes memory migrateData = abi.encodeCall(StrategyVault.migrateVerifier, (a.newTAV));
        for (uint256 i = 0; i < proxies.length; i++) {
            IUUPS(proxies[i]).upgradeToAndCall(a.newStrategyVaultImpl, migrateData);
        }

        vm.stopBroadcast();

        _log(a, proxies);
        _patchJson(string.concat("./deployments/", label, ".json"), a);
    }

    function _patchJson(string memory file, Out memory a) internal {
        _writeAddr(file, ".addresses.tradeAttestationVerifier", a.newTAV);
        _writeAddr(file, ".addresses.momentumVerifier", a.newMomentumVerifier);
        _writeAddr(file, ".addresses.momentumVerifierAdapter", a.newMomentumAdapter);
        _writeAddr(file, ".addresses.meanReversionVerifier", a.newMeanReversionVerifier);
        _writeAddr(file, ".addresses.meanReversionVerifierAdapter", a.newMeanReversionAdapter);
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

    function _log(Out memory a, address[] memory proxies) internal view {
        console2.log("=== Phase 6 #13: TAV redeploy + 9-vault migrate ===");
        console2.log("chainId:                          ", block.chainid);
        console2.log("new TradeAttestationVerifier:     ", a.newTAV);
        console2.log("new MomentumV1Verifier:           ", a.newMomentumVerifier);
        console2.log("new MomentumV1VerifierAdapter:    ", a.newMomentumAdapter);
        console2.log("new MeanReversionV1Verifier:      ", a.newMeanReversionVerifier);
        console2.log("new MeanReversionV1VerifierAdapter:", a.newMeanReversionAdapter);
        console2.log("yieldRotation adapter (unchanged):", a.yieldRotationAdapter);
        console2.log("new StrategyVault impl:           ", a.newStrategyVaultImpl);
        for (uint256 i = 0; i < proxies.length; i++) {
            console2.log("upgraded + migrated proxy:        ", proxies[i]);
        }
    }

    function _proxies() internal view returns (address[] memory out) {
        string memory env = vm.envOr("PROXIES", string(""));
        if (bytes(env).length == 0) {
            out = new address[](_DEFAULT_PROXIES.length);
            for (uint256 i = 0; i < _DEFAULT_PROXIES.length; i++) {
                out[i] = _DEFAULT_PROXIES[i];
            }
            return out;
        }
        bytes memory b = bytes(env);
        uint256 count = 1;
        for (uint256 i = 0; i < b.length; i++) {
            if (b[i] == ",") count++;
        }
        out = new address[](count);
        uint256 idx = 0;
        uint256 start = 0;
        for (uint256 i = 0; i <= b.length; i++) {
            if (i == b.length || b[i] == ",") {
                bytes memory slice = new bytes(i - start);
                for (uint256 j = 0; j < slice.length; j++) {
                    slice[j] = b[start + j];
                }
                out[idx++] = vm.parseAddress(string(slice));
                start = i + 1;
            }
        }
    }

    function _chainName() internal view returns (string memory) {
        if (block.chainid == 2368) return "kite-testnet";
        if (block.chainid == 84_532) return "base-sepolia";
        if (block.chainid == 421_614) return "arbitrum-sepolia";
        if (block.chainid == 31_337) return "anvil-kite-phase2";
        return "unknown-chain";
    }
}
