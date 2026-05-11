// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";
import { StrategyVault } from "src/StrategyVault.sol";
import { StrategyRegistry } from "src/StrategyRegistry.sol";

/// @notice Two-step recovery for vaults with stranded NAV:
///         (1) UUPS-upgrade the proxy to a `StrategyVault` impl that
///             carries `recoverStrandedNAV` (the function was added
///             after the original Phase-6 deploy);
///         (2) Sweep the residual `_totalNAV` to the recipient and
///             attempt `StrategyRegistry.deactivate` — which had been
///             reverting `StrategyHasActiveCapital` while NAV > 0.
///
///         Env:
///           STRATEGY_VAULT_IMPL    — newly-deployed impl with recover fn
///           STRATEGY_VAULT_PROXY   — proxy holding the stranded NAV
///           STRATEGY_REGISTRY_V1   — registry to deactivate from (or 0x0)
///           STRANDED_RECIPIENT     — where to forward the swept balance
///           DEPLOYER_PK            — proxy owner (must equal vault.owner())
///
///         Idempotent: re-running after a successful sweep is a no-op
///         (recoverStrandedNAV reverts `WithdrawExceedsNAVShare` on 0).
contract RecoverStrandedNAVScript is Script {
    function run() external {
        address impl = vm.envAddress("STRATEGY_VAULT_IMPL");
        address proxy = vm.envAddress("STRATEGY_VAULT_PROXY");
        address registry = vm.envOr("STRATEGY_REGISTRY_V1", address(0));
        address recipient = vm.envAddress("STRANDED_RECIPIENT");
        uint256 pk = vm.envUint("DEPLOYER_PK");

        StrategyVault vault = StrategyVault(proxy);

        vm.startBroadcast(pk);

        // 1. UUPS-upgrade if the proxy isn't already on the new impl.
        //    We can't read the impl slot directly without a helper; just
        //    attempt the upgrade. ERC1967Proxy disallows upgrading to
        //    the same impl, so a `try/catch` keeps idempotency.
        try vault.upgradeToAndCall(impl, "") {
            console2.log("upgraded   ", proxy, "->", impl);
        } catch {
            console2.log("upgrade noop (already at impl)", proxy);
        }

        // 2. Sweep stranded NAV.
        uint256 stranded = vault.totalNAV();
        console2.log("stranded   ", stranded);
        if (stranded > 0) {
            vault.recoverStrandedNAV(recipient, stranded);
            console2.log("recovered  ", stranded, "->", recipient);
        }

        // 3. Try to deactivate in the registry. If the vault isn't
        //    registered there, `deactivate` reverts — we tolerate
        //    that since the caller can pass STRATEGY_REGISTRY_V1=0x0.
        if (registry != address(0)) {
            try StrategyRegistry(registry).deactivate(proxy) {
                console2.log("deactivated in registry", registry);
            } catch {
                console2.log("deactivate noop / not allowed", registry);
            }
        }

        vm.stopBroadcast();
    }
}
