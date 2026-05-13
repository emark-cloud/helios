// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";
import { MUsdcOFTAdapter } from "../src/MUsdcOFTAdapter.sol";

/// @notice CXR-0a — Deploy MUsdcOFTAdapter on Kite, Arbitrum-Sepolia, or
///         Base-Sepolia. The adapter wraps the local mUSDC `0xe8cf8a57…`
///         for LayerZero V2 cross-chain transfers. Inventory pre-funding
///         (~100k mUSDC) is performed in a separate broadcast after the
///         adapter address is known.
///
///         Required env:
///           - DEPLOYER_PK
///           - LZ_ENDPOINT  (LZ V2 endpoint address for the target chain)
///
///         Side-effect on `<chain>.json`:
///           - addresses.mUsdcOFTAdapter
contract DeployOFTAdapter is Script {
    function run() external returns (address adapter) {
        uint256 chainId = block.chainid;
        require(
            chainId == 2368 || chainId == 421614 || chainId == 84532,
            "DeployOFTAdapter: unsupported chain"
        );

        uint256 pk = vm.envUint("DEPLOYER_PK");
        address deployer = vm.addr(pk);
        address endpoint = vm.envAddress("LZ_ENDPOINT");

        string memory file;
        if (chainId == 2368) {
            file = "./deployments/kite-testnet.json";
        } else if (chainId == 421614) {
            file = "./deployments/arbitrum-sepolia.json";
        } else {
            file = "./deployments/base-sepolia.json";
        }

        address mUsdc = _readAddress(file, ".addresses.usdc");
        require(mUsdc != address(0), "mUSDC missing");

        vm.startBroadcast(pk);
        MUsdcOFTAdapter a = new MUsdcOFTAdapter(mUsdc, endpoint, deployer);
        vm.stopBroadcast();

        adapter = address(a);

        console2.log("=== CXR-0a MUsdcOFTAdapter ===");
        console2.log("chainId:  ", chainId);
        console2.log("deployer: ", deployer);
        console2.log("endpoint: ", endpoint);
        console2.log("mUSDC:    ", mUsdc);
        console2.log("adapter:  ", adapter);

        vm.writeJson(
            string.concat('"', vm.toString(adapter), '"'), file, ".addresses.mUsdcOFTAdapter"
        );
        console2.log("patched:", file);
    }

    function _readAddress(string memory file, string memory key) internal view returns (address) {
        string memory json = vm.readFile(file);
        bytes memory raw = vm.parseJson(json, key);
        return abi.decode(raw, (address));
    }
}
