// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";
import { MUsdcOFTAdapter } from "../src/MUsdcOFTAdapter.sol";

/// @notice CXR-0a — Wire LayerZero V2 OFT peers bidirectionally between
///         Kite, Arbitrum-Sepolia, and Base-Sepolia. Must be run on the
///         local chain after every adapter has been broadcast and its
///         address recorded in the per-chain deployments JSON.
///
///         For each remote chain, this calls
///         `setPeer(remoteEid, bytes32(uint256(uint160(remoteAdapter))))`
///         on the local adapter. Owner-only.
///
///         Required env:
///           - DEPLOYER_PK   (must equal adapter owner)
///
///         Reads from the local deployment JSON to find the local
///         adapter address; reads the other two chain JSONs to find the
///         remote adapters + EIDs.
contract WireOFTPeers is Script {
    uint32 internal constant KITE_EID = 40_415;
    uint32 internal constant ARB_EID = 40_231;
    uint32 internal constant BASE_EID = 40_245;

    function run() external {
        uint256 chainId = block.chainid;
        require(
            chainId == 2368 || chainId == 421_614 || chainId == 84_532, "WireOFTPeers: unsupported"
        );

        uint256 pk = vm.envUint("DEPLOYER_PK");

        (string memory localFile, uint32 localEid) = _chainCtx(chainId);
        address localAdapter = _readAddress(localFile, ".addresses.mUsdcOFTAdapter");
        require(localAdapter != address(0), "local adapter missing");

        (uint32[2] memory remoteEids, address[2] memory remoteAdapters) = _remotes(chainId);

        vm.startBroadcast(pk);
        MUsdcOFTAdapter adapter = MUsdcOFTAdapter(localAdapter);
        for (uint256 i; i < remoteEids.length; i++) {
            if (remoteAdapters[i] == address(0)) continue; // skip not-yet-broadcast chains
            adapter.setPeer(remoteEids[i], bytes32(uint256(uint160(remoteAdapters[i]))));
            console2.log("wired peer:", remoteEids[i], remoteAdapters[i]);
        }
        vm.stopBroadcast();

        console2.log("=== CXR-0a OFT peers wired ===");
        console2.log("local chain:  ", chainId);
        console2.log("local EID:    ", localEid);
        console2.log("local adapter:", localAdapter);
    }

    function _chainCtx(uint256 chainId) internal pure returns (string memory file, uint32 eid) {
        if (chainId == 2368) return ("./deployments/kite-testnet.json", KITE_EID);
        if (chainId == 421_614) return ("./deployments/arbitrum-sepolia.json", ARB_EID);
        return ("./deployments/base-sepolia.json", BASE_EID);
    }

    function _remotes(uint256 chainId)
        internal
        view
        returns (uint32[2] memory eids, address[2] memory adapters)
    {
        if (chainId == 2368) {
            eids = [ARB_EID, BASE_EID];
            adapters = [
                _readAddress("./deployments/arbitrum-sepolia.json", ".addresses.mUsdcOFTAdapter"),
                _readAddress("./deployments/base-sepolia.json", ".addresses.mUsdcOFTAdapter")
            ];
        } else if (chainId == 421_614) {
            eids = [KITE_EID, BASE_EID];
            adapters = [
                _readAddress("./deployments/kite-testnet.json", ".addresses.mUsdcOFTAdapter"),
                _readAddress("./deployments/base-sepolia.json", ".addresses.mUsdcOFTAdapter")
            ];
        } else {
            eids = [KITE_EID, ARB_EID];
            adapters = [
                _readAddress("./deployments/kite-testnet.json", ".addresses.mUsdcOFTAdapter"),
                _readAddress("./deployments/arbitrum-sepolia.json", ".addresses.mUsdcOFTAdapter")
            ];
        }
    }

    function _readAddress(string memory file, string memory key) internal view returns (address) {
        // Tolerate missing key (key absent from older deployment JSONs)
        try vm.readFile(file) returns (string memory json) {
            bytes memory raw = vm.parseJson(json, key);
            if (raw.length == 0) return address(0);
            return abi.decode(raw, (address));
        } catch {
            return address(0);
        }
    }
}
