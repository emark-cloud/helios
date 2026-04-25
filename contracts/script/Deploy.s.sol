// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";
import { Helios } from "../src/Helios.sol";

/// @notice Phase 0 deploy: confirms the deploy pipeline against Kite testnet.
///         Records the deployed address under deployments/<chain>.json.
contract Deploy is Script {
    function run() external {
        uint256 pk = vm.envUint("DEPLOYER_PK");
        vm.startBroadcast(pk);
        Helios helios = new Helios();
        vm.stopBroadcast();

        console2.log("Helios deployed at:", address(helios));
        console2.log("Chain id:", block.chainid);

        string memory json = string.concat(
            '{\n  "chainId": ',
            vm.toString(block.chainid),
            ',\n  "helios": "',
            vm.toString(address(helios)),
            '",\n  "deployedAt": ',
            vm.toString(block.timestamp),
            "\n}\n"
        );

        string memory file = string.concat("./deployments/", _chainName(), ".json");
        vm.writeFile(file, json);
    }

    function _chainName() internal view returns (string memory) {
        if (block.chainid == 2368) return "kite-testnet";
        if (block.chainid == 84_532) return "base-sepolia";
        if (block.chainid == 421_614) return "arbitrum-sepolia";
        if (block.chainid == 31_337) return "anvil";
        return vm.toString(block.chainid);
    }
}
