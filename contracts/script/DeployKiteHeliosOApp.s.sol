// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";
import { HeliosOApp } from "../src/HeliosOApp.sol";

/// @notice Phase-5 canonical-side HeliosOApp deploy (Kite testnet).
///
///         `DeployPhase5Execution.s.sol` ships execution-chain shape:
///         `reputationAnchor_ = address(0)`. The canonical-side OApp on Kite
///         must point at the live `ReputationAnchor` so that inbound
///         `ReputationUpdateV1` packets land via `postCrossChainUpdate`. This
///         script does that single piece. Phase-5 surface on Kite is
///         otherwise served by the existing Phase-1/2/6 contracts already
///         deployed at the addresses in `deployments/kite-testnet.json`.
///
///         Patches the existing `deployments/kite-testnet.json` in place
///         (does NOT rewrite it). Adds:
///           - `lzLocalEid` (top-level; expected by WireLayerZeroPeers)
///           - `lzKiteEndpoint` (top-level; informational)
///           - `addresses.heliosOApp`
///
///         Required env:
///           - DEPLOYER_PK
///           - LZ_ENDPOINT_KITE   (LZ V2 endpoint, e.g.
///                                 0x3aCAAf60502791D199a5a5F0B173D78229eBFe32)
///           - LZ_KITE_EID        (local EID, e.g. 40415)
contract DeployKiteHeliosOApp is Script {
    /// @dev Canonical Kite ReputationAnchor V1 (registry-bound; immutable).
    ///      Source: contracts/deployments/kite-testnet.json @
    ///      addresses.reputationAnchor. Pinned here to keep the broadcast
    ///      script side-effect-free against the JSON read.
    address internal constant KITE_REPUTATION_ANCHOR = 0x51C07aDf596B1e72697a9B8232d061ed006943Dc;

    /// @dev Matches DeployPhase5Execution constructor arg.
    uint256 internal constant MAX_PENDING = 64;

    function run() external returns (address heliosOApp) {
        uint256 pk = vm.envUint("DEPLOYER_PK");
        address deployer = vm.addr(pk);
        address endpoint = vm.envAddress("LZ_ENDPOINT_KITE");
        uint32 kiteEid = uint32(vm.envUint("LZ_KITE_EID"));

        require(block.chainid == 2368, "DeployKiteHeliosOApp: not Kite testnet");

        vm.startBroadcast(pk);
        heliosOApp = address(
            new HeliosOApp(endpoint, deployer, kiteEid, KITE_REPUTATION_ANCHOR, MAX_PENDING)
        );
        vm.stopBroadcast();

        console2.log("=== Helios Kite-side HeliosOApp deploy ===");
        console2.log("chainId:                ", block.chainid);
        console2.log("endpoint:               ", endpoint);
        console2.log("lz local EID (kiteEid): ", kiteEid);
        console2.log("reputationAnchor:       ", KITE_REPUTATION_ANCHOR);
        console2.log("HeliosOApp:             ", heliosOApp);

        _patchDeploymentJson(heliosOApp, kiteEid, endpoint);
    }

    /// @dev Surgically patches the existing kite-testnet.json. The third-arg
    ///      form of `vm.writeJson` takes a JSON-formatted value (numbers
    ///      unquoted, strings wrapped in escaped quotes) and a JSONPath key.
    function _patchDeploymentJson(address oApp, uint32 localEid, address endpoint) internal {
        string memory file = "./deployments/kite-testnet.json";
        vm.writeJson(vm.toString(uint256(localEid)), file, ".lzLocalEid");
        vm.writeJson(string.concat('"', vm.toString(endpoint), '"'), file, ".lzKiteEndpoint");
        vm.writeJson(string.concat('"', vm.toString(oApp), '"'), file, ".addresses.heliosOApp");
        console2.log("patched:", file);
    }
}
