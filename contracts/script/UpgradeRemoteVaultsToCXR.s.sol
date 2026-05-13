// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";
import { StrategyVault } from "../src/StrategyVault.sol";

interface IUUPS {
    function upgradeToAndCall(address newImplementation, bytes memory data) external;
}

/// @notice CXR-0b followup — deploy a CXR-aware StrategyVault impl on
///         Arb-Sepolia and upgrade the existing yr.arb proxy
///         (`0x516f23B9d2…`) so its `bridgeReceiver` slot becomes
///         settable. The yr.arb proxy was deployed against the
///         pre-CXR-0b impl `0x78b3515f…` which predates the new
///         storage slots — calling `bridgeReceiver()` on it reverts.
///
///         Storage layout is append-only (3 new slots before `__gap`;
///         gap shrunk 45→42), so the upgrade preserves existing state.
///
///         Required env:
///           - DEPLOYER_PK   funded testnet key (must own the proxy)
///
///         Reads from `./deployments/arbitrum-sepolia.json`:
///           - phase6VaultYieldRotationArb (proxy)
///           - oraclePriceAnchor, oracleYieldAnchor (for impl constructor)
///
///         Patches `strategyVaultImplCXR` in the same JSON.
contract UpgradeRemoteVaultsToCXR is Script {
    string internal constant FILE = "./deployments/arbitrum-sepolia.json";

    function run() external {
        require(block.chainid == 421_614, "UpgradeRemoteVaultsToCXR: not Arb-Sepolia");

        uint256 pk = vm.envUint("DEPLOYER_PK");
        address proxy = _readAddress(".addresses.phase6VaultYieldRotationArb");
        address priceAnchor = _readAddress(".addresses.oraclePriceAnchor");
        address yieldAnchor = _readAddress(".addresses.oracleYieldAnchor");

        require(proxy != address(0), "yr.arb proxy missing");
        require(priceAnchor != address(0), "priceAnchor missing");
        require(yieldAnchor != address(0), "yieldAnchor missing");

        vm.startBroadcast(pk);
        StrategyVault impl = new StrategyVault(priceAnchor, yieldAnchor);
        IUUPS(proxy).upgradeToAndCall(address(impl), "");
        vm.stopBroadcast();

        console2.log("=== CXR-0b Arb remote impl upgrade ===");
        console2.log("yr.arb proxy:        ", proxy);
        console2.log("new CXR-aware impl:  ", address(impl));

        vm.writeJson(
            string.concat('"', vm.toString(address(impl)), '"'),
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
