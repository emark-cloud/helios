// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";

import { StrategyRegistry } from "../src/StrategyRegistry.sol";
import { IStrategyVault } from "../src/interfaces/IStrategyVault.sol";

/// @notice Phase-6 cutover: deactivate the nine legacy single-asset
///         StrategyVaults so allocators ignore them once the new
///         multi-asset vaults are live. Kept apart from the redeploy
///         script so it can be reverted independently if a regression
///         is found in the new vaults.
///
///         StrategyRegistry.deactivate requires:
///           1. msg.sender == operator   (deployer in Phase 1+)
///           2. vault.totalNAV() == 0    (operators must defund first)
///         If totalNAV is non-zero the call reverts; the script
///         pre-flights each vault and skips any that still hold capital,
///         logging a clear warning so the operator knows to defund and
///         re-run.
contract DeactivateLegacyVaults is Script {
    /// @dev Order matches kite-testnet.json's nine legacy entries.
    struct LegacyVaults {
        address momentum;
        address momentumVariant2;
        address momentumVariant3;
        address meanReversion;
        address meanReversionVariant2;
        address meanReversionVariant3;
        address yieldRotation;
        address yieldRotationVariant2;
        address yieldRotationVariant3;
    }

    function run() external {
        uint256 pk = vm.envUint("DEPLOYER_PK");
        address strategyRegistry = vm.envAddress("STRATEGY_REGISTRY");
        LegacyVaults memory legacy = _loadLegacy();

        vm.startBroadcast(pk);
        _deactivate(strategyRegistry, legacy.momentum, "mom.base");
        _deactivate(strategyRegistry, legacy.momentumVariant2, "mom.variant2");
        _deactivate(strategyRegistry, legacy.momentumVariant3, "mom.variant3");
        _deactivate(strategyRegistry, legacy.meanReversion, "mr.base");
        _deactivate(strategyRegistry, legacy.meanReversionVariant2, "mr.variant2");
        _deactivate(strategyRegistry, legacy.meanReversionVariant3, "mr.variant3");
        _deactivate(strategyRegistry, legacy.yieldRotation, "yr.base");
        _deactivate(strategyRegistry, legacy.yieldRotationVariant2, "yr.variant2");
        _deactivate(strategyRegistry, legacy.yieldRotationVariant3, "yr.variant3");
        vm.stopBroadcast();
    }

    function _loadLegacy() internal view returns (LegacyVaults memory l) {
        l.momentum = vm.envAddress("LEGACY_MOM");
        l.momentumVariant2 = vm.envAddress("LEGACY_MOM_V2");
        l.momentumVariant3 = vm.envAddress("LEGACY_MOM_V3");
        l.meanReversion = vm.envAddress("LEGACY_MR");
        l.meanReversionVariant2 = vm.envAddress("LEGACY_MR_V2");
        l.meanReversionVariant3 = vm.envAddress("LEGACY_MR_V3");
        l.yieldRotation = vm.envAddress("LEGACY_YR");
        l.yieldRotationVariant2 = vm.envAddress("LEGACY_YR_V2");
        l.yieldRotationVariant3 = vm.envAddress("LEGACY_YR_V3");
    }

    function _deactivate(address registry, address vault, string memory label) internal {
        // Pre-flight: skip if the vault still holds capital. The registry
        // check would revert with StrategyHasActiveCapital; surfacing it
        // as a log lets the rest of the cutover continue and gives the
        // operator a clear list of which vaults need a defund pass.
        try IStrategyVault(vault).totalNAV() returns (uint256 nav) {
            if (nav > 0) {
                console2.log(
                    string.concat("SKIP[", label, "] holds NAV (defund first):"), vault, nav
                );
                return;
            }
        } catch {
            console2.log(string.concat("SKIP[", label, "] totalNAV() reverted:"), vault);
            return;
        }

        StrategyRegistry(registry).deactivate(vault);
        console2.log(string.concat("deactivated[", label, "]:"), vault);
    }
}
