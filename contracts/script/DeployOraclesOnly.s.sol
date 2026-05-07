// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";

import { OraclePriceAnchor } from "../src/OraclePriceAnchor.sol";
import { OracleYieldAnchor } from "../src/OracleYieldAnchor.sol";

/// @title DeployOraclesOnly
/// @notice Phase-3 review HIGH #6/#9 redeployed the two oracle anchors with
///         a `_committedAt` mapping, `unrevokeRoot()` and `freshness()`.
///         The deployed anchors are immutable (non-upgradeable), so we
///         redeploy and patch kite-testnet.json. The proxy-side
///         repointing (StrategyVault.priceAnchor / yieldAnchor) is
///         handled by a follow-up upgrade script that bakes the new
///         anchor addresses into the impl bytecode (PR #65 made the
///         anchors constructor immutables).
///
///         Required env:
///           - DEPLOYER_PK    funded testnet key (becomes owner)
///           - PRICE_SIGNER   off-chain oracle signer for prices
///           - YIELD_SIGNER   off-chain oracle signer for yields
///         Optional:
///           - OUT_LABEL      deployments/<label>.json (defaults to chain name)
contract DeployOraclesOnly is Script {
    struct Out {
        address oraclePriceAnchor;
        address oracleYieldAnchor;
    }

    function run() external returns (Out memory a) {
        uint256 pk = vm.envUint("DEPLOYER_PK");
        address deployer = vm.addr(pk);
        address priceSigner = vm.envAddress("PRICE_SIGNER");
        address yieldSigner = vm.envAddress("YIELD_SIGNER");
        string memory label = vm.envOr("OUT_LABEL", _chainName());

        vm.startBroadcast(pk);
        a.oraclePriceAnchor = address(new OraclePriceAnchor(priceSigner, deployer));
        a.oracleYieldAnchor = address(new OracleYieldAnchor(yieldSigner, deployer));
        vm.stopBroadcast();

        _log(a, deployer, priceSigner, yieldSigner);
        _patchJson(string.concat("./deployments/", label, ".json"), a);
    }

    function _patchJson(string memory file, Out memory a) internal {
        _writeAddr(file, ".addresses.oraclePriceAnchor", a.oraclePriceAnchor);
        _writeAddr(file, ".addresses.oracleYieldAnchor", a.oracleYieldAnchor);
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

    function _log(Out memory a, address deployer, address priceSigner, address yieldSigner)
        internal
        view
    {
        console2.log("=== oracles-only redeploy ===");
        console2.log("chainId:                    ", block.chainid);
        console2.log("deployer/owner:             ", deployer);
        console2.log("priceSigner:                ", priceSigner);
        console2.log("yieldSigner:                ", yieldSigner);
        console2.log("OraclePriceAnchor:          ", a.oraclePriceAnchor);
        console2.log("OracleYieldAnchor:          ", a.oracleYieldAnchor);
    }

    function _chainName() internal view returns (string memory) {
        if (block.chainid == 2368) return "kite-testnet";
        if (block.chainid == 84_532) return "base-sepolia";
        if (block.chainid == 421_614) return "arbitrum-sepolia";
        if (block.chainid == 31_337) return "anvil-kite-phase2";
        return "unknown-chain";
    }
}
