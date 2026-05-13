// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";
import { HeliosBridgeReceiver } from "../src/HeliosBridgeReceiver.sol";

/// @notice CXR-0b — Deploy HeliosBridgeReceiver on Kite, Arb-Sepolia, or
///         Base-Sepolia. Wires the receiver to the local OFTAdapter +
///         mUSDC + LZ endpoint.
///
///         On Kite, the deployer should then call
///         `receiver.setAllocatorVault(<AllocatorVault>)` so the
///         SETTLE_DEFUND path can credit the canonical accounting
///         layer. Left zero on Arb/Base (defunds originate there, never
///         land there).
///
///         Required env:
///           - DEPLOYER_PK
///           - LZ_ENDPOINT  (LZ V2 endpoint address)
///
///         Reads `addresses.usdc` + `addresses.mUsdcOFTAdapter` from
///         the local deployments JSON; patches
///         `addresses.heliosBridgeReceiver`.
contract DeployBridgeReceiver is Script {
    function run() external returns (address receiver) {
        uint256 chainId = block.chainid;
        require(
            chainId == 2368 || chainId == 421_614 || chainId == 84_532,
            "DeployBridgeReceiver: unsupported chain"
        );

        uint256 pk = vm.envUint("DEPLOYER_PK");
        address deployer = vm.addr(pk);
        address endpoint = vm.envAddress("LZ_ENDPOINT");

        string memory file;
        if (chainId == 2368) {
            file = "./deployments/kite-testnet.json";
        } else if (chainId == 421_614) {
            file = "./deployments/arbitrum-sepolia.json";
        } else {
            file = "./deployments/base-sepolia.json";
        }

        address usdc = _readAddress(file, ".addresses.usdc");
        address adapter = _readAddress(file, ".addresses.mUsdcOFTAdapter");
        require(usdc != address(0), "usdc missing");
        require(adapter != address(0), "mUsdcOFTAdapter missing (run DeployOFTAdapter first)");

        vm.startBroadcast(pk);
        HeliosBridgeReceiver r = new HeliosBridgeReceiver(usdc, endpoint, adapter, deployer);
        vm.stopBroadcast();

        receiver = address(r);

        console2.log("=== CXR-0b HeliosBridgeReceiver ===");
        console2.log("chainId: ", chainId);
        console2.log("deployer:", deployer);
        console2.log("endpoint:", endpoint);
        console2.log("usdc:    ", usdc);
        console2.log("adapter: ", adapter);
        console2.log("receiver:", receiver);

        vm.writeJson(
            string.concat('"', vm.toString(receiver), '"'), file, ".addresses.heliosBridgeReceiver"
        );
        console2.log("patched:", file);
    }

    function _readAddress(string memory file, string memory key) internal view returns (address) {
        string memory json = vm.readFile(file);
        bytes memory raw = vm.parseJson(json, key);
        if (raw.length == 0) return address(0);
        return abi.decode(raw, (address));
    }
}
