// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";
import { ReputationAnchorV2 } from "../src/ReputationAnchorV2.sol";
import { StrategyRegistry } from "../src/StrategyRegistry.sol";
import { AllocatorRegistry } from "../src/AllocatorRegistry.sol";
import { IERC20 } from "@openzeppelin/contracts/token/ERC20/IERC20.sol";

/// @notice WS11 — full V1→V2 ReputationAnchor cutover (Phase 6).
///
///         Deploys a fresh `ReputationAnchorV2` (v2-bis) and the two
///         registries whose immutable `reputationAnchor` field points
///         at v2-bis, then wires v2-bis to those registries via the
///         one-shot `setRegistries`. The existing V2 anchor
///         (`0x735680a3…`) is locked to V1 registries by an earlier
///         (foot-gun) `setRegistries(V1, V1)` call — see
///         `docs/reputation-v1-v2-cutover.md`.
///
///         Side-effect on `kite-testnet.json` (additive — no key
///         overwrites the WS10 set):
///           - `addresses.reputationAnchorV2Bis`
///           - `addresses.strategyRegistryV3`
///           - `addresses.allocatorRegistryV2`
///
///         Required env:
///           - DEPLOYER_PK
///           - REPUTATION_SIGNER     (signer EOA for the v2-bis EIP-712
///                                    typehash; off-chain engine signer)
///
///         Notes:
///           - `oApp` is left as `address(0)` initially; WS11.6 deploys
///             the new Kite OApp pointing at v2-bis, then calls
///             `v2bis.setOApp(newKiteOApp)`.
///           - `stakeToken` is read from the existing V1 registries on
///             chain so the new registries share the same mUSDC.
///           - `stakeCooldown` mirrors V1 at 7 days.
contract DeployReputationCutover is Script {
    uint256 internal constant STAKE_COOLDOWN = 7 days;

    /// @dev Live V1 StrategyRegistry on Kite — read for `stakeToken`.
    address internal constant V1_STRATEGY_REGISTRY = 0x3A0f5B9436EcA0c8C0ECed659Dcc41E86E65E33D;

    function run()
        external
        returns (address anchorV2Bis, address strategyRegistryV3, address allocatorRegistryV2)
    {
        uint256 pk = vm.envUint("DEPLOYER_PK");
        address deployer = vm.addr(pk);
        address signer = vm.envAddress("REPUTATION_SIGNER");

        require(block.chainid == 2368, "DeployReputationCutover: not Kite testnet");

        // Read the shared stake token from V1 so SR-v3 / AR-v2 stay
        // ABI-compatible with existing user-facing flows.
        IERC20 stakeToken = StrategyRegistry(V1_STRATEGY_REGISTRY).stakeToken();
        require(address(stakeToken) != address(0), "stakeToken read failed");

        vm.startBroadcast(pk);

        // (1) Fresh anchor. oApp left zero — WS11.6 wires it.
        ReputationAnchorV2 anchor = new ReputationAnchorV2(signer, address(0), deployer);

        // (2) Registries point at v2-bis at construction.
        StrategyRegistry strategyRegistry =
            new StrategyRegistry(stakeToken, address(anchor), deployer, STAKE_COOLDOWN);

        AllocatorRegistry allocatorRegistry =
            new AllocatorRegistry(stakeToken, address(anchor), deployer, STAKE_COOLDOWN);

        // (3) One-shot wire. After this `setRegistries` reverts
        // `RegistriesAlreadySet` on the same anchor instance.
        anchor.setRegistries(address(strategyRegistry), address(allocatorRegistry));

        vm.stopBroadcast();

        anchorV2Bis = address(anchor);
        strategyRegistryV3 = address(strategyRegistry);
        allocatorRegistryV2 = address(allocatorRegistry);

        console2.log("=== WS11 ReputationAnchor cutover ===");
        console2.log("chainId:                ", block.chainid);
        console2.log("deployer:               ", deployer);
        console2.log("signer:                 ", signer);
        console2.log("stakeToken:             ", address(stakeToken));
        console2.log("reputationAnchorV2Bis:  ", anchorV2Bis);
        console2.log("strategyRegistryV3:     ", strategyRegistryV3);
        console2.log("allocatorRegistryV2:    ", allocatorRegistryV2);

        _patchDeploymentJson(anchorV2Bis, strategyRegistryV3, allocatorRegistryV2);
    }

    function _patchDeploymentJson(address anchor, address sr, address ar) internal {
        string memory file = "./deployments/kite-testnet.json";
        vm.writeJson(
            string.concat('"', vm.toString(anchor), '"'), file, ".addresses.reputationAnchorV2Bis"
        );
        vm.writeJson(
            string.concat('"', vm.toString(sr), '"'), file, ".addresses.strategyRegistryV3"
        );
        vm.writeJson(
            string.concat('"', vm.toString(ar), '"'), file, ".addresses.allocatorRegistryV2"
        );
        console2.log("patched:", file);
    }
}
