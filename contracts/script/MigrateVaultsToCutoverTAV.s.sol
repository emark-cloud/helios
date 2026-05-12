// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";

import { StrategyVault } from "../src/StrategyVault.sol";

interface IUUPS {
    function upgradeToAndCall(address newImplementation, bytes memory data) external;
}

/// @title MigrateVaultsToCutoverTAV
/// @notice Phase-6 cross-decimal cutover step 2 (companion to
///         `DeployCrossDecimalCutover.s.sol`). Deploys a fresh
///         `StrategyVault` impl carrying the 16-PI directional path +
///         decimals-honesty guard, then UUPS-upgrades each of the
///         currently-active Phase-6 strategy-vault proxies with
///         `upgradeToAndCall(newImpl, migrateVerifier(newTAV))` so the
///         impl swap + verifier rebind land atomically per proxy.
///
///         Required env:
///           - DEPLOYER_PK        proxy owner (also funds gas)
///           - PRICE_ANCHOR       current OraclePriceAnchor
///           - YIELD_ANCHOR       current OracleYieldAnchor
///           - NEW_TAV            new TradeAttestationVerifier from cutover
///         Optional:
///           - PROXIES            comma-separated proxy list (override)
///           - OUT_LABEL          deployments/<label>.json target
contract MigrateVaultsToCutoverTAV is Script {
    address[9] internal _DEFAULT_PROXIES = [
        0xA44Ef042840C8C4F1a174Daf66389EFEb8375a5a, // momentum base (dedicated-op)
        0x7A18727375065B29526d816b713fAD99cD247006, // momentum V2
        0xecfeB975789Cf058865830f985bA18299d8e1DCA, // momentum V3
        0x1717640c4f9Cd9f84B028Bc8DFDceA3fB0572c6a, // mean-rev base (dedicated-op)
        0x4509C3E7b5e418c0701cf4D0145c570bAc2f8fCA, // mean-rev V2
        0x125B10809e3c6d70c51bF6385eD3CFb1C771D0F5, // mean-rev V3
        0x2AfF8735Ed89451d359205DC6a80ae625E6F6E47, // yield base
        0x7ed482Adcc6951Bc2058dd45cC26D15b3d585deB, // yield V2
        0x76a50fE4C5585a13bE311ecA135D0Ab8f39b434d // yield V3
    ];

    struct Out {
        address newStrategyVaultImpl;
    }

    function run() external returns (Out memory a) {
        uint256 pk = vm.envUint("DEPLOYER_PK");
        address priceAnchor = vm.envAddress("PRICE_ANCHOR");
        address yieldAnchor = vm.envAddress("YIELD_ANCHOR");
        address newTAV = vm.envAddress("NEW_TAV");
        string memory label = vm.envOr("OUT_LABEL", _chainName());
        address[] memory proxies = _proxies();

        vm.startBroadcast(pk);

        a.newStrategyVaultImpl = address(new StrategyVault(priceAnchor, yieldAnchor));

        bytes memory migrateData = abi.encodeCall(StrategyVault.migrateVerifier, (newTAV));
        for (uint256 i = 0; i < proxies.length; i++) {
            IUUPS(proxies[i]).upgradeToAndCall(a.newStrategyVaultImpl, migrateData);
        }

        vm.stopBroadcast();

        _log(a, proxies, newTAV);
        _patchJson(string.concat("./deployments/", label, ".json"), a, newTAV);
    }

    function _patchJson(string memory file, Out memory a, address newTAV) internal {
        _writeAddr(file, ".addresses.strategyVaultImplCrossDecimal", a.newStrategyVaultImpl);
        _writeAddr(file, ".addresses.tradeAttestationVerifier", newTAV);
        console2.log("merged into:", file);
    }

    function _writeAddr(string memory file, string memory path, address v) internal {
        vm.writeJson(string.concat('"', _addrLower(v), '"'), file, path);
    }

    function _addrLower(address v) internal pure returns (string memory) {
        bytes memory hexChars = "0123456789abcdef";
        bytes20 b = bytes20(v);
        bytes memory out = new bytes(42);
        out[0] = "0";
        out[1] = "x";
        for (uint256 i = 0; i < 20; i++) {
            out[2 + i * 2] = hexChars[uint8(b[i] >> 4)];
            out[3 + i * 2] = hexChars[uint8(b[i] & 0x0f)];
        }
        return string(out);
    }

    function _log(Out memory a, address[] memory proxies, address newTAV) internal view {
        console2.log("=== Phase-6 cross-decimal cutover (vault migrate) ===");
        console2.log("chainId:                  ", block.chainid);
        console2.log("new TAV (bound):          ", newTAV);
        console2.log("new StrategyVault impl:   ", a.newStrategyVaultImpl);
        for (uint256 i = 0; i < proxies.length; i++) {
            console2.log("upgraded + migrated proxy:", proxies[i]);
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
                for (uint256 j = 0; j < slice.length; j++) {
                    slice[j] = b[start + j];
                }
                out[idx++] = vm.parseAddress(string(slice));
                start = i + 1;
            }
        }
    }

    function _chainName() internal view returns (string memory) {
        if (block.chainid == 2368) return "kite-testnet";
        if (block.chainid == 84_532) return "base-sepolia";
        if (block.chainid == 421_614) return "arbitrum-sepolia";
        if (block.chainid == 31_337) return "anvil-kite-phase2";
        return "unknown-chain";
    }
}
