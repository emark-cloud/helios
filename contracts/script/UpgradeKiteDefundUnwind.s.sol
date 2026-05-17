// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";
import { AllocatorVault } from "../src/AllocatorVault.sol";
import { StrategyVault } from "../src/StrategyVault.sol";

interface IUUPS {
    function upgradeToAndCall(address newImplementation, bytes memory data) external;
}

/// @notice Defund-unwind rollout — upgrade the Kite AllocatorVault +
///         all 9 Phase-6 StrategyVault proxies to impls carrying the
///         privileged proof-less `StrategyVault.unwindToBase()` and the
///         `AllocatorVault._unwindAndCredit` hook that calls it, so a
///         defund of an in-position vault no longer reverts
///         `ERC20InsufficientBalance` (live: mean_reversion
///         `0x1717640c`, user `0x1cFC…`).
///
///         FUNCTION-ONLY change — zero storage delta on BOTH contracts
///         (`MAX_UNWIND_SLIPPAGE_BPS` is a constant; new events/error
///         are bytecode-only). `__gap` is untouched, so
///         `upgradeToAndCall(impl, "")` is append-safe; new state
///         slots: none. Mirrors the NAV-counter-saturation rollout
///         (impl `0xe13BfCD4…`).
///
///         Required env:
///           - DEPLOYER_PK   funded testnet key (must own every proxy)
///
///         Reads proxy addresses from `./deployments/kite-testnet.json`
///         and patches the new impl addresses under
///         `addresses.allocatorVaultImplDefundUnwind` and
///         `addresses.strategyVaultImplDefundUnwind`.
contract UpgradeKiteDefundUnwind is Script {
    string internal constant FILE = "./deployments/kite-testnet.json";

    function run() external {
        require(block.chainid == 2368, "UpgradeKiteDefundUnwind: not Kite");

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
        require(allocatorVaultProxy != address(0), "missing AllocatorVault proxy");

        vm.startBroadcast(pk);
        AllocatorVault avImpl = new AllocatorVault();
        StrategyVault svImpl = new StrategyVault(
            _readAddress(".addresses.oraclePriceAnchor"),
            _readAddress(".addresses.oracleYieldAnchor")
        );

        IUUPS(allocatorVaultProxy).upgradeToAndCall(address(avImpl), "");
        console2.log("upgraded AllocatorVault:", allocatorVaultProxy);

        for (uint256 i; i < svProxies.length; i++) {
            require(svProxies[i] != address(0), "missing SV proxy");
            IUUPS(svProxies[i]).upgradeToAndCall(address(svImpl), "");
            console2.log("upgraded SV:", svProxies[i]);
        }
        vm.stopBroadcast();

        console2.log("=== Defund-unwind Kite upgrades ===");
        console2.log("AllocatorVault proxy:", allocatorVaultProxy);
        console2.log("AllocatorVault impl: ", address(avImpl));
        console2.log("StrategyVault impl:  ", address(svImpl));

        vm.writeJson(
            string.concat('"', vm.toString(address(avImpl)), '"'),
            FILE,
            ".addresses.allocatorVaultImplDefundUnwind"
        );
        vm.writeJson(
            string.concat('"', vm.toString(address(svImpl)), '"'),
            FILE,
            ".addresses.strategyVaultImplDefundUnwind"
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
