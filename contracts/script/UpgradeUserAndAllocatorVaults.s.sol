// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";

import { UserVault } from "../src/UserVault.sol";
import { AllocatorVault } from "../src/AllocatorVault.sol";

interface IUUPS {
    function upgradeToAndCall(address newImplementation, bytes memory data) external;
}

/// @title UpgradeUserAndAllocatorVaults
/// @notice Phase-3 review HIGH #5 / #8 / #10 changed UserVault and
///         AllocatorVault behavior:
///           - UserVault: setMeta tightening guard reading
///             AllocatorVault.userTotalDeployed (HIGH #5)
///           - AllocatorVault: userTotalDeployed view +
///             capped _unwindAndCredit (HIGH #8)
///           - Both: PausableUpgradeable mixin (HIGH #10)
///
///         Pausable uses ERC-7201 namespaced storage
///         (slot derived from keccak256("openzeppelin.storage.Pausable")),
///         so the new impls are append-only on inherited storage and need
///         no re-init — the namespaced slot defaults to _paused = false on
///         first read. upgradeToAndCall is invoked with empty data.
///
///         Required env:
///           - DEPLOYER_PK    funded testnet key (must own both proxies)
///         Optional env:
///           - USER_VAULT       override default Kite testnet proxy
///           - ALLOCATOR_VAULT  override default Kite testnet proxy
///
///         Recommended pre-flight:
///           forge inspect UserVault storage-layout
///           forge inspect AllocatorVault storage-layout
///         Diff against the deployed bytecode must be empty or
///         appended-only (Pausable namespaced slot is invisible to the
///         layout dump — that is expected).
contract UpgradeUserAndAllocatorVaults is Script {
    address internal constant DEFAULT_USER_VAULT = 0x78b3515f4e9186d9870dcEF02DA58E4C8c5C6e8f;
    address internal constant DEFAULT_ALLOCATOR_VAULT = 0xf3E4452FE17edBFA6833022B9c186aa14b98955d;

    function run() external {
        uint256 pk = vm.envUint("DEPLOYER_PK");
        address userVaultProxy = vm.envOr("USER_VAULT", DEFAULT_USER_VAULT);
        address allocatorVaultProxy = vm.envOr("ALLOCATOR_VAULT", DEFAULT_ALLOCATOR_VAULT);

        vm.startBroadcast(pk);
        UserVault uvImpl = new UserVault();
        AllocatorVault avImpl = new AllocatorVault();
        IUUPS(userVaultProxy).upgradeToAndCall(address(uvImpl), "");
        IUUPS(allocatorVaultProxy).upgradeToAndCall(address(avImpl), "");
        vm.stopBroadcast();

        console2.log("=== UserVault + AllocatorVault UUPS upgrade ===");
        console2.log("chainId:                  ", block.chainid);
        console2.log("UserVault proxy:          ", userVaultProxy);
        console2.log("UserVault impl (new):     ", address(uvImpl));
        console2.log("AllocatorVault proxy:     ", allocatorVaultProxy);
        console2.log("AllocatorVault impl (new):", address(avImpl));
    }
}
