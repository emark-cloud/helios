// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";

import { StrategyVault } from "../src/StrategyVault.sol";

interface IUUPS {
    function upgradeToAndCall(address newImplementation, bytes memory data) external;
}

/// @title UpgradeStrategyVaultsOnly
/// @notice Phase-3 review HIGH #6 / #8 / #10 changed StrategyVault behavior:
///         oracle freshness check, NAV-cap on `withdrawToAllocator`,
///         Pausable mixin. These ride on a UUPS upgrade. PR #65 made
///         priceAnchor / yieldAnchor constructor immutables on the impl,
///         so deploying a fresh impl with the new (Phase-3 redeployed)
///         anchor addresses atomically repoints all upgraded proxies.
///
///         One impl, nine proxies — the bytecode is identical for every
///         strategy vault (anchors are the same). Each `upgradeToAndCall`
///         passes empty data (no re-init needed; proxy storage carries
///         the existing manifest, registry, etc.).
///
///         Required env:
///           - DEPLOYER_PK    funded testnet key (must own every proxy)
///           - PRICE_ANCHOR   new OraclePriceAnchor address
///           - YIELD_ANCHOR   new OracleYieldAnchor address
///         Optional:
///           - PROXIES        comma-separated list (defaults to the nine
///                            Kite testnet strategy vaults).
contract UpgradeStrategyVaultsOnly is Script {
    address[9] internal _DEFAULT_PROXIES = [
        0x818A782f040f09389E7C34B1e2e33188D473a950, // momentum base
        0xc1B19Df0003eaDF29313826DC874c769Ebb09109, // momentum V2
        0x4e19e5EeC25fc15FBC30A9446d283f4EBeD6462C, // momentum V3
        0x6C1F9466db7Bc2364b0baC051E73421d5b75354B, // mean-rev base
        0xD4898262Bb6FfBaF5F0C016663a2C59767DDb65F, // mean-rev V2
        0x50c1DCC21E571c106eEE21f42f22FB6eA0d4a708, // mean-rev V3
        0xbFBf9fa82B5DF3B080BE27F64D650101Ee69C36F, // yield base
        0x5605B2E1883428680266fD25cb7429f2001c0c17, // yield V2
        0x3863f44FE693764562c0d239e05C5F194544B0B4 // yield V3
    ];

    function run() external {
        uint256 pk = vm.envUint("DEPLOYER_PK");
        address priceAnchor = vm.envAddress("PRICE_ANCHOR");
        address yieldAnchor = vm.envAddress("YIELD_ANCHOR");

        address[] memory proxies = _proxies();

        vm.startBroadcast(pk);
        StrategyVault impl = new StrategyVault(priceAnchor, yieldAnchor);
        for (uint256 i = 0; i < proxies.length; i++) {
            IUUPS(proxies[i]).upgradeToAndCall(address(impl), "");
        }
        vm.stopBroadcast();

        console2.log("=== StrategyVault UUPS upgrade ===");
        console2.log("chainId:                  ", block.chainid);
        console2.log("priceAnchor (immutable):  ", priceAnchor);
        console2.log("yieldAnchor (immutable):  ", yieldAnchor);
        console2.log("new StrategyVault impl:   ", address(impl));
        for (uint256 i = 0; i < proxies.length; i++) {
            console2.log("upgraded proxy:           ", proxies[i]);
        }
    }

    function _proxies() internal view returns (address[] memory out) {
        string memory env = vm.envOr("PROXIES", string(""));
        if (bytes(env).length == 0) {
            out = new address[](_DEFAULT_PROXIES.length);
            for (uint256 i = 0; i < _DEFAULT_PROXIES.length; i++) {
                out[i] = _DEFAULT_PROXIES[i];
            }
            return out;
        }
        bytes memory b = bytes(env);
        uint256 count = 1;
        for (uint256 i = 0; i < b.length; i++) {
            if (b[i] == ",") count++;
        }
        out = new address[](count);
        uint256 idx = 0;
        uint256 start = 0;
        for (uint256 i = 0; i <= b.length; i++) {
            if (i == b.length || b[i] == ",") {
                bytes memory slice = new bytes(i - start);
                for (uint256 j = 0; j < slice.length; j++) slice[j] = b[start + j];
                out[idx++] = vm.parseAddress(string(slice));
                start = i + 1;
            }
        }
    }
}
