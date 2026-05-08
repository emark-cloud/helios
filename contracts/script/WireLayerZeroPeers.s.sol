// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";

import { HeliosOApp } from "../src/HeliosOApp.sol";

/// @notice Phase-5 LayerZero V2 peer-wiring script. Run **after** all three
///         chains have been deployed (`DeployPhase5Execution` on Base + Arb;
///         the canonical-side OApp deployed alongside Phase-3 / extended in a
///         future Phase-5 patch). For each pair of chains, calls
///         `HeliosOApp.setPeer(remoteEid, bytes32(uint160(remoteOApp)))` so
///         each direction is mutually trusted.
///
///         The script runs *one chain at a time* — the broadcast flag must
///         match the chain whose JSON the script is reading from. Re-running
///         per chain is idempotent because `setPeer` is owner-only and
///         updates the peer mapping in place.
///
///         Required env (per-run):
///           - DEPLOYER_PK         (current chain's owner of HeliosOApp)
///           - WIRE_PEER_FILES     comma-separated list of *other* chains'
///                                 deployment JSONs to read remote
///                                 (eid, oApp) pairs from. Example:
///                                 "deployments/kite-testnet.json,deployments/arbitrum-sepolia.json"
///         Optional env:
///           - LOCAL_LABEL         (default: derived from chainid; reads
///                                 `deployments/<label>.json` for *this*
///                                 chain's HeliosOApp + lzLocalEid)
///
///         phase5-plan.md §WS2.
contract WireLayerZeroPeers is Script {
    function run() external {
        uint256 pk = vm.envUint("DEPLOYER_PK");
        string memory localLabel = vm.envOr("LOCAL_LABEL", _chainName());
        string memory localFile = string.concat("./deployments/", localLabel, ".json");
        string memory localRaw = vm.readFile(localFile);

        address localOApp = vm.parseJsonAddress(localRaw, ".addresses.heliosOApp");
        require(localOApp != address(0), "WireLayerZeroPeers: local oApp not deployed");

        string memory remotesCsv = vm.envString("WIRE_PEER_FILES");
        string[] memory remoteFiles = _splitCsv(remotesCsv);
        require(remoteFiles.length > 0, "WireLayerZeroPeers: WIRE_PEER_FILES empty");

        vm.startBroadcast(pk);
        for (uint256 i = 0; i < remoteFiles.length; i++) {
            (uint32 remoteEid, address remoteOApp) = _readRemote(remoteFiles[i]);
            require(remoteOApp != address(0), "WireLayerZeroPeers: remote oApp empty");
            require(remoteEid != 0, "WireLayerZeroPeers: remote eid empty");

            bytes32 peer = bytes32(uint256(uint160(remoteOApp)));
            HeliosOApp(localOApp).setPeer(remoteEid, peer);

            console2.log("setPeer:", remoteFiles[i]);
            console2.log("  remoteEid:  ", remoteEid);
            console2.log("  remoteOApp: ", remoteOApp);
        }
        vm.stopBroadcast();
    }

    function _readRemote(string memory file) internal view returns (uint32 eid, address oApp) {
        string memory raw = vm.readFile(file);
        // Both Phase-5 execution-chain JSONs ship `lzLocalEid`; the canonical
        // (Kite) JSON does not yet have one — when `lzLocalEid` is absent we
        // fall back to `lzKiteEid` written from this side's deploy artifacts.
        eid = uint32(vm.parseJsonUint(raw, ".lzLocalEid"));
        oApp = vm.parseJsonAddress(raw, ".addresses.heliosOApp");
    }

    function _splitCsv(string memory csv) internal pure returns (string[] memory out) {
        bytes memory b = bytes(csv);
        // Count commas first so we can size `out` exactly.
        uint256 n = 1;
        for (uint256 i = 0; i < b.length; i++) {
            if (b[i] == ",") n++;
        }
        out = new string[](n);
        uint256 idx;
        uint256 start;
        for (uint256 i = 0; i <= b.length; i++) {
            if (i == b.length || b[i] == ",") {
                bytes memory slice = new bytes(i - start);
                for (uint256 j = 0; j < slice.length; j++) {
                    slice[j] = b[start + j];
                }
                out[idx++] = string(slice);
                start = i + 1;
            }
        }
    }

    function _chainName() internal view returns (string memory) {
        if (block.chainid == 2368) return "kite-testnet";
        if (block.chainid == 84_532) return "base-sepolia";
        if (block.chainid == 421_614) return "arbitrum-sepolia";
        if (block.chainid == 31_337) return "anvil";
        return vm.toString(block.chainid);
    }
}
