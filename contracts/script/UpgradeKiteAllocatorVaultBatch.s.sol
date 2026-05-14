// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";
import { AllocatorVault } from "../src/AllocatorVault.sol";

interface IUUPS {
    function upgradeToAndCall(address newImplementation, bytes memory data) external;
}

/// @notice CXR-cost Tier 2 — Upgrade the Kite AllocatorVault impl to
///         one that exposes `allocateToRemoteStrategyBatch`. Same
///         storage layout as CXR-0c (no new state slots — Tier 2 adds
///         only constants + a new external entrypoint, no proxy
///         storage). Existing `allocateToRemoteStrategy` shim stays
///         intact for single-strategy paths.
///
///         Caller-driven cutover: after this script lands, the
///         allocator-sdk's `_flush_cross_chain_group` will start
///         calling the batch entrypoint when N>1 same-destination
///         strategies are eligible in one tick. Single-call shape is
///         unchanged for N==1, so a partial cutover (impl upgraded
///         but sdk pinned to old shape) is safe.
contract UpgradeKiteAllocatorVaultBatch is Script {
    string internal constant FILE = "./deployments/kite-testnet.json";

    function run() external {
        require(block.chainid == 2368, "UpgradeKiteAllocatorVaultBatch: not Kite");
        uint256 pk = vm.envUint("DEPLOYER_PK");
        address proxy = _readAddress(".addresses.allocatorVault");

        vm.startBroadcast(pk);
        AllocatorVault impl = new AllocatorVault();
        IUUPS(proxy).upgradeToAndCall(address(impl), "");
        vm.stopBroadcast();

        console2.log("=== CXR-cost Tier 2 AllocatorVault upgrade ===");
        console2.log("AllocatorVault proxy:", proxy);
        console2.log("New impl (batch):   ", address(impl));

        vm.writeJson(
            string.concat('"', vm.toString(address(impl)), '"'),
            FILE,
            ".addresses.allocatorVaultImplBatch"
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
