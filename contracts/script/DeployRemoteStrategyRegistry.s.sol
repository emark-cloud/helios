// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";
import { StrategyRegistry } from "../src/StrategyRegistry.sol";
import { IERC20 } from "@openzeppelin/contracts/token/ERC20/IERC20.sol";

/// @notice CXR-1 — Deploy a local StrategyRegistry on Arbitrum-Sepolia or
///         Base-Sepolia so the per-chain StrategyVault proxies have a
///         registry to bind paramsHashOf / marketAllowlistRoot against.
///
///         Per Helios.md §12.1, identity (and therefore the registry of
///         record) is per-chain. Reputation flows cross-chain via
///         HeliosOApp; the per-chain registries never receive
///         updateReputation calls, so `reputationAnchor_` is passed as
///         the local HeliosOApp address purely to satisfy the
///         constructor's non-zero check.
///
///         Required env:
///           - DEPLOYER_PK
///
///         Side-effect on `{arbitrum,base}-sepolia.json`:
///           - addresses.strategyRegistry
contract DeployRemoteStrategyRegistry is Script {
    uint256 internal constant STAKE_COOLDOWN = 7 days;

    function run() external returns (address strategyRegistry) {
        uint256 chainId = block.chainid;
        require(
            chainId == 421614 || chainId == 84532, "DeployRemoteStrategyRegistry: unsupported chain"
        );

        uint256 pk = vm.envUint("DEPLOYER_PK");
        address deployer = vm.addr(pk);

        string memory file = chainId == 421614
            ? "./deployments/arbitrum-sepolia.json"
            : "./deployments/base-sepolia.json";

        IERC20 stakeToken = IERC20(_readAddress(file, ".addresses.usdc"));
        address oApp = _readAddress(file, ".addresses.heliosOApp");
        require(address(stakeToken) != address(0), "stake token missing");
        require(oApp != address(0), "oApp missing");

        vm.startBroadcast(pk);
        StrategyRegistry sr = new StrategyRegistry(stakeToken, oApp, deployer, STAKE_COOLDOWN);
        vm.stopBroadcast();

        strategyRegistry = address(sr);

        console2.log("=== CXR-1 Remote StrategyRegistry ===");
        console2.log("chainId:          ", chainId);
        console2.log("deployer:         ", deployer);
        console2.log("stakeToken:       ", address(stakeToken));
        console2.log("anchorPlaceholder:", oApp);
        console2.log("strategyRegistry: ", strategyRegistry);

        vm.writeJson(
            string.concat('"', vm.toString(strategyRegistry), '"'),
            file,
            ".addresses.strategyRegistry"
        );
        console2.log("patched:", file);
    }

    function _readAddress(string memory file, string memory key) internal view returns (address) {
        string memory json = vm.readFile(file);
        bytes memory raw = vm.parseJson(json, key);
        return abi.decode(raw, (address));
    }
}
