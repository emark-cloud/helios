// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";
import { AllocatorVault } from "../src/AllocatorVault.sol";

interface IUUPS {
    function upgradeToAndCall(address newImplementation, bytes memory data) external;
}

/// @notice CXR-0c — Upgrade the Kite AllocatorVault impl to one that
///         reads `destinationReceiver[dstEid]` for the OFT `to:`
///         target instead of the single-valued `bridgeReceiver` slot.
///
///         Storage layout: append-only. CXR-0c adds 1 new map slot
///         (`destinationReceiver`); gap shrinks 41 → 40.
///
///         No new state to seed at upgrade time. Caller separately
///         runs `setDestinationReceiver(uint32, address)` for each
///         supported dst EID after this script.
contract UpgradeKiteAllocatorVaultCXR0c is Script {
    string internal constant FILE = "./deployments/kite-testnet.json";

    function run() external {
        require(block.chainid == 2368, "UpgradeKiteAllocatorVaultCXR0c: not Kite");
        uint256 pk = vm.envUint("DEPLOYER_PK");
        address proxy = _readAddress(".addresses.allocatorVault");

        vm.startBroadcast(pk);
        AllocatorVault impl = new AllocatorVault();
        IUUPS(proxy).upgradeToAndCall(address(impl), "");
        vm.stopBroadcast();

        console2.log("=== CXR-0c AllocatorVault upgrade ===");
        console2.log("AllocatorVault proxy:", proxy);
        console2.log("New impl:           ", address(impl));

        vm.writeJson(
            string.concat('"', vm.toString(address(impl)), '"'),
            FILE,
            ".addresses.allocatorVaultImplCXR0c"
        );
        console2.log("patched:", FILE);
    }

    function _readAddress(string memory key) internal view returns (address) {
        string memory json = vm.readFile(FILE);
        bytes memory raw = vm.parseJson(json, key);
        if (raw.length == 0) return address(0);
        return abi.decode(raw, (address));
    }
}
