// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";

import { MockTestToken } from "../test/mocks/MockTestToken.sol";

/// @notice Phase-6 real-P&L workstream 1: deploy the test-asset universe
///         (mWBTC, mWETH, mSOL) and seed MockSwapRouter inventory so the
///         downstream multi-asset StrategyVault redeploy has something to
///         swap against. Existing mUSDC is left alone — the new vaults
///         keep using it as the base asset.
///
///         Inventory seed sized for >> $10M-equivalent at typical demo
///         spot prices (BTC ~$50k, ETH ~$3k, SOL ~$150) so a $1k Maya
///         deposit can't drain any leg over the demo window.
///
///         Outputs: appends a `testAssets` block to
///         contracts/deployments/<chain>.json without touching legacy
///         keys (the JSON merge mirrors RegisterFreshStrategy.s.sol).
contract DeployTestUniverse is Script {
    /// @dev Inventory amounts in raw (decimals-aware) units.
    uint256 internal constant SEED_WBTC = 1_000 * 10 ** 8; // 1k BTC
    uint256 internal constant SEED_WETH = 50_000 * 10 ** 18; // 50k ETH
    uint256 internal constant SEED_SOL = 1_000_000 * 10 ** 9; // 1M SOL

    struct Outputs {
        address mWbtc;
        address mWeth;
        address mSol;
    }

    function run() external returns (Outputs memory o) {
        uint256 pk = vm.envUint("DEPLOYER_PK");
        address deployer = vm.addr(pk);
        address swapRouter = vm.envAddress("SWAP_ROUTER");
        string memory label = vm.envOr("OUT_LABEL", _chainName());

        vm.startBroadcast(pk);
        o = _deployTokens(deployer);
        _seedRouter(o, swapRouter);
        vm.stopBroadcast();

        _logAndPersist(o, label, swapRouter);
    }

    function _deployTokens(address deployer) internal returns (Outputs memory o) {
        MockTestToken wbtc = new MockTestToken("Helios Mock WBTC", "mWBTC", 8);
        MockTestToken weth = new MockTestToken("Helios Mock WETH", "mWETH", 18);
        MockTestToken sol = new MockTestToken("Helios Mock SOL", "mSOL", 9);

        // Mint generous deployer inventory so future top-ups don't need
        // a fresh deploy — the deployer wallet stays the universe-asset
        // mint authority (MockTestToken.mint is permissionless anyway).
        wbtc.mint(deployer, SEED_WBTC);
        weth.mint(deployer, SEED_WETH);
        sol.mint(deployer, SEED_SOL);

        o.mWbtc = address(wbtc);
        o.mWeth = address(weth);
        o.mSol = address(sol);
    }

    function _seedRouter(Outputs memory o, address swapRouter) internal {
        MockTestToken(o.mWbtc).transfer(swapRouter, SEED_WBTC);
        MockTestToken(o.mWeth).transfer(swapRouter, SEED_WETH);
        MockTestToken(o.mSol).transfer(swapRouter, SEED_SOL);
    }

    function _logAndPersist(Outputs memory o, string memory label, address swapRouter) internal {
        console2.log("=== Helios Phase-6 test universe ===");
        console2.log("mWBTC:        ", o.mWbtc);
        console2.log("mWETH:        ", o.mWeth);
        console2.log("mSOL:         ", o.mSol);
        console2.log("MockSwapRouter:", swapRouter);

        string memory file = string.concat("./deployments/", label, ".json");
        _patchJson(file, o);
        console2.log("merged into:", file);
    }

    /// @dev Read-merge-write the deployments JSON: preserve every existing
    ///      key under `addresses.*`, append the three new test-asset
    ///      addresses, and stamp `phase6TestUniverseDeployedAt`.
    ///      Re-runs are idempotent (existing keys with the same name are
    ///      replaced, not duplicated).
    function _patchJson(string memory file, Outputs memory o) internal {
        string memory raw = vm.readFile(file);
        uint256 chainIdVal = vm.parseJsonUint(raw, ".chainId");
        uint256 deployedAtVal = vm.parseJsonUint(raw, ".deployedAt");

        string memory addrsBody = _existingAddresses(raw);
        addrsBody = string.concat(addrsBody, _kv("mWbtc", o.mWbtc));
        addrsBody = string.concat(addrsBody, _kv("mWeth", o.mWeth));
        addrsBody = string.concat(addrsBody, _kvLast("mSol", o.mSol));

        string memory merged = string.concat(
            "{\n",
            '  "chainId": ',
            vm.toString(chainIdVal),
            ",\n",
            '  "deployedAt": ',
            vm.toString(deployedAtVal),
            ',\n  "phase": "6",\n',
            '  "phase6TestUniverseDeployedAt": ',
            vm.toString(block.timestamp),
            ',\n  "addresses": {\n',
            addrsBody,
            "  }\n}\n"
        );
        vm.writeFile(file, merged);
    }

    function _existingAddresses(string memory raw) internal pure returns (string memory body) {
        string[] memory keys = vm.parseJsonKeys(raw, ".addresses");
        bytes32 wbtcKey = keccak256("mWbtc");
        bytes32 wethKey = keccak256("mWeth");
        bytes32 solKey = keccak256("mSol");
        for (uint256 i = 0; i < keys.length; i++) {
            string memory k = keys[i];
            bytes32 h = keccak256(bytes(k));
            if (h == wbtcKey || h == wethKey || h == solKey) continue; // dedupe on re-run
            address val = vm.parseJsonAddress(raw, string.concat(".addresses.", k));
            body = string.concat(body, _kv(k, val));
        }
    }

    function _kv(string memory k, address v) internal pure returns (string memory) {
        return string.concat('    "', k, '": "', _addrLower(v), '",\n');
    }

    function _kvLast(string memory k, address v) internal pure returns (string memory) {
        return string.concat('    "', k, '": "', _addrLower(v), '"\n');
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

    function _chainName() internal view returns (string memory) {
        if (block.chainid == 2368) return "kite-testnet";
        if (block.chainid == 84_532) return "base-sepolia";
        if (block.chainid == 421_614) return "arbitrum-sepolia";
        if (block.chainid == 31_337) return "anvil";
        return vm.toString(block.chainid);
    }
}
