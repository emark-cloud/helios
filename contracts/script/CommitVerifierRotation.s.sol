// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";

import { ClassIds } from "../src/ClassIds.sol";
import { TradeAttestationVerifier } from "../src/TradeAttestationVerifier.sol";

/// @title CommitVerifierRotation
/// @notice Companion to `ProposeVerifierRotation`. Run AFTER the 2-day
///         `CHANGE_DELAY` has elapsed. Reverts via TAV with `ChangeNotReady`
///         if the eta hasn't passed yet, so it's safe to invoke speculatively.
///
///         After a successful commit, the script patches
///         `deployments/<network>.json` with the new verifier + adapter
///         addresses. The propose-side script logs those addresses; pass
///         them in via env vars so the JSON patch happens in a single tx.
///
///         Required env:
///           - DEPLOYER_PK                          funded testnet key (TAV owner)
///           - TRADE_VERIFIER                       existing TAV address
///           - MOMENTUM_VERIFIER_NEW                from propose log
///           - MOMENTUM_VERIFIER_ADAPTER_NEW        from propose log
///           - MEAN_REVERSION_VERIFIER_NEW          from propose log
///           - MEAN_REVERSION_VERIFIER_ADAPTER_NEW  from propose log
///         Optional:
///           - OUT_LABEL                            deployments/<label>.json target
contract CommitVerifierRotation is Script {
    bytes32 internal constant CLASS_MOM = ClassIds.MOMENTUM_V1;
    bytes32 internal constant CLASS_MR = ClassIds.MEAN_REVERSION_V1;

    function run() external {
        uint256 pk = vm.envUint("DEPLOYER_PK");
        TradeAttestationVerifier tav = TradeAttestationVerifier(vm.envAddress("TRADE_VERIFIER"));
        address momV = vm.envAddress("MOMENTUM_VERIFIER_NEW");
        address momA = vm.envAddress("MOMENTUM_VERIFIER_ADAPTER_NEW");
        address mrV = vm.envAddress("MEAN_REVERSION_VERIFIER_NEW");
        address mrA = vm.envAddress("MEAN_REVERSION_VERIFIER_ADAPTER_NEW");
        string memory label = vm.envOr("OUT_LABEL", _chainName());

        vm.startBroadcast(pk);
        tav.commitVerifierChange(CLASS_MOM);
        tav.commitVerifierChange(CLASS_MR);
        vm.stopBroadcast();

        require(tav.verifierByClassMap(CLASS_MOM) == momA, "momentum class map mismatch");
        require(tav.verifierByClassMap(CLASS_MR) == mrA, "mean-reversion class map mismatch");

        string memory file = string.concat("./deployments/", label, ".json");
        _writeAddr(file, ".addresses.momentumVerifier", momV);
        _writeAddr(file, ".addresses.momentumVerifierAdapter", momA);
        _writeAddr(file, ".addresses.meanReversionVerifier", mrV);
        _writeAddr(file, ".addresses.meanReversionVerifierAdapter", mrA);

        console2.log("=== verifier-rotation commit ===");
        console2.log("chainId:                        ", block.chainid);
        console2.log("verifierByClassMap[mom]:        ", tav.verifierByClassMap(CLASS_MOM));
        console2.log("verifierByClassMap[mr]:         ", tav.verifierByClassMap(CLASS_MR));
        console2.log("merged into:                    ", file);
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
        if (block.chainid == 84_532) return "base-sepolia";
        if (block.chainid == 421_614) return "arbitrum-sepolia";
        if (block.chainid == 31_337) return "anvil-kite-phase2";
        return "unknown-chain";
    }
}
