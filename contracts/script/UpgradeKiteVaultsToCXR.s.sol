// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";
import { AllocatorVault } from "../src/AllocatorVault.sol";
import { StrategyVault } from "../src/StrategyVault.sol";

interface IUUPS {
    function upgradeToAndCall(address newImplementation, bytes memory data) external;
}

/// @notice CXR-0b — Upgrade Kite AllocatorVault + all 9 Phase-6
///         StrategyVault proxies to impls that carry the cross-chain
///         allocate/defund hooks. Storage layout is append-only:
///
///         AllocatorVault gains 3 slots before `__gap`:
///           - bridgeReceiver (address)
///           - oftAdapter (address)
///           - _userRemoteDeployed (mapping)
///         Gap shrinks 44 → 41.
///
///         StrategyVault gains 3 slots before `__gap`:
///           - bridgeReceiver (address)
///           - oftAdapter (address)
///           - totalCrossChainAllocated (uint256)
///         Gap shrinks 45 → 42.
///
///         `upgradeToAndCall` is invoked with empty data — new state
///         slots default to 0 / address(0) and are wired post-upgrade
///         via `set*` functions in `WireCXRReceivers.s.sol`.
///
///         Required env:
///           - DEPLOYER_PK   funded testnet key (must own every proxy)
///
///         Reads proxy addresses from
///         `./deployments/kite-testnet.json`. Patches the new impl
///         addresses under `addresses.allocatorVaultImplCXR` and
///         `addresses.strategyVaultImplCXR`.
contract UpgradeKiteVaultsToCXR is Script {
    string internal constant FILE = "./deployments/kite-testnet.json";

    function run() external {
        require(block.chainid == 2368, "UpgradeKiteVaultsToCXR: not Kite");

        uint256 pk = vm.envUint("DEPLOYER_PK");
        address allocatorVaultProxy = _readAddress(".addresses.allocatorVault");

        address[9] memory svProxies = [
            _readAddress(".addresses.phase6VaultMomentum"),
            _readAddress(".addresses.phase6VaultMomentumVariant2"),
            _readAddress(".addresses.phase6VaultMomentumVariant3"),
            _readAddress(".addresses.phase6VaultMeanReversion"),
            _readAddress(".addresses.phase6VaultMeanReversionVariant2"),
            _readAddress(".addresses.phase6VaultMeanReversionVariant3"),
            _readAddress(".addresses.phase6VaultYieldRotation"),
            _readAddress(".addresses.phase6VaultYieldRotationVariant2"),
            _readAddress(".addresses.phase6VaultYieldRotationVariant3")
        ];

        vm.startBroadcast(pk);
        AllocatorVault avImpl = new AllocatorVault();
        StrategyVault svImpl = new StrategyVault(
            _readAddress(".addresses.oraclePriceAnchor"),
            _readAddress(".addresses.oracleYieldAnchor")
        );

        IUUPS(allocatorVaultProxy).upgradeToAndCall(address(avImpl), "");

        for (uint256 i; i < svProxies.length; i++) {
            require(svProxies[i] != address(0), "missing SV proxy");
            IUUPS(svProxies[i]).upgradeToAndCall(address(svImpl), "");
            console2.log("upgraded SV:", svProxies[i]);
        }
        vm.stopBroadcast();

        console2.log("=== CXR-0b Kite upgrades ===");
        console2.log("AllocatorVault proxy:", allocatorVaultProxy);
        console2.log("AllocatorVault impl: ", address(avImpl));
        console2.log("StrategyVault impl:  ", address(svImpl));

        vm.writeJson(
            string.concat('"', vm.toString(address(avImpl)), '"'),
            FILE,
            ".addresses.allocatorVaultImplCXR"
        );
        vm.writeJson(
            string.concat('"', vm.toString(address(svImpl)), '"'),
            FILE,
            ".addresses.strategyVaultImplCXR"
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
