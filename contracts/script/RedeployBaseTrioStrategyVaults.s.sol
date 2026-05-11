// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";
import { ERC1967Proxy } from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";

import { StrategyRegistry } from "../src/StrategyRegistry.sol";
import { StrategyVault } from "../src/StrategyVault.sol";
import { IStrategyVault } from "../src/interfaces/IStrategyVault.sol";
import { MockERC20 } from "../test/mocks/MockERC20.sol";
import { ClassIds } from "../src/ClassIds.sol";

/// @notice Phase-3 follow-up: fresh-deploy the three base StrategyVault
///         proxies on the Phase-3 impl. The original base trio
///         (`strategyVaultMomentum` / `strategyVaultMeanReversion` /
///         `strategyVaultYieldRotation`) was deployed before commit
///         `a4b844a` added `bytes32 paramsHash` mid-struct on 2026-04-28,
///         so its `_manifest` is one slot shorter than the Phase-3 impl
///         expects. UUPS-upgrading them would corrupt storage. The only
///         safe path is fresh proxies.
///
///         This script is the base-trio analogue of the retired
///         RegisterPhase2Strategies script — same impl
///         (`StrategyVault(priceAnchor, yieldAnchor)`, constructor
///         immutables → Phase-3 oracle anchors), one new proxy per class,
///         each with its own paramsHash so the cohort accounting still
///         splits cleanly against the existing variant2 + variant3
///         strategies.
///
///         What this script does NOT do:
///           - does NOT touch the existing Variant2 / Variant3 proxies
///             (already on Phase-3 impl)
///           - does NOT deactivate the legacy base-trio in
///             StrategyRegistry — leave that as an explicit operator
///             decision (`deactivate(<legacyVault>)` on the registry)
///           - does NOT swap or redeploy verifiers / oracles / vaults
///             other than the three new strategy proxies
///
///         JSON merge: overwrites `strategyVaultMomentum`,
///         `strategyVaultMeanReversion`, `strategyVaultYieldRotation`
///         in `deployments/<chain>.json`. Legacy proxy addresses drop
///         out of the JSON (recoverable from git history) and remain on
///         chain, registered but unreferenced.
///
///         Required env:
///           - DEPLOYER_PK
///           - USDC
///           - STRATEGY_REGISTRY
///           - ALLOCATOR_VAULT
///           - TRADE_VERIFIER
///           - SWAP_ROUTER
///           - ORACLE_PRICE_ANCHOR    (Phase-3 redeploy: 0x566e1f1b…)
///           - ORACLE_YIELD_ANCHOR    (Phase-3 redeploy: 0x345cd375…)
///         Optional env:
///           - OUT_LABEL              (default: chain name)
contract RedeployBaseTrioStrategyVaults is Script {
    bytes32 internal constant CLASS_MOM = ClassIds.MOMENTUM_V1;
    bytes32 internal constant CLASS_MR = ClassIds.MEAN_REVERSION_V1;
    bytes32 internal constant CLASS_YR = ClassIds.YIELD_ROTATION_V1;

    uint16 internal constant STRATEGY_FEE_BPS = 1000; // 10% — matches Phase-1 primary
    uint256 internal constant STRATEGY_STAKE = 5000e6; // 5k USDC — matches Phase-1
    uint256 internal constant MAX_CAPACITY = 1_000_000e6;

    /// @dev Distinct paramsHash per class so cohort math separates these
    ///      from the existing variant2 + variant3 strategies. The
    ///      "phase3-redeploy" tag makes the lineage obvious in subgraph
    ///      queries that key on paramsHash.
    bytes32 internal constant PARAMS_HASH_MOM_BASE =
        keccak256("helios.mom_v1.base.phase3-redeploy");
    bytes32 internal constant PARAMS_HASH_MR_BASE = keccak256("helios.mr_v1.base.phase3-redeploy");
    bytes32 internal constant PARAMS_HASH_YR_BASE = keccak256("helios.yr_v1.base.phase3-redeploy");

    struct Inputs {
        uint256 deployerPk;
        address usdc;
        address strategyRegistry;
        address allocatorVault;
        address tradeVerifier;
        address swapRouter;
        address oraclePriceAnchor;
        address oracleYieldAnchor;
        string outLabel;
    }

    struct BaseTrioAddresses {
        address strategyVaultMomentum;
        address strategyVaultMeanReversion;
        address strategyVaultYieldRotation;
    }

    function run() external returns (BaseTrioAddresses memory v) {
        uint256 pk = vm.envUint("DEPLOYER_PK");
        Inputs memory i = Inputs({
            deployerPk: pk,
            usdc: vm.envAddress("USDC"),
            strategyRegistry: vm.envAddress("STRATEGY_REGISTRY"),
            allocatorVault: vm.envAddress("ALLOCATOR_VAULT"),
            tradeVerifier: vm.envAddress("TRADE_VERIFIER"),
            swapRouter: vm.envAddress("SWAP_ROUTER"),
            oraclePriceAnchor: vm.envAddress("ORACLE_PRICE_ANCHOR"),
            oracleYieldAnchor: vm.envAddress("ORACLE_YIELD_ANCHOR"),
            outLabel: vm.envOr("OUT_LABEL", _chainName())
        });
        return runWith(i);
    }

    function runWith(Inputs memory i) public returns (BaseTrioAddresses memory v) {
        address deployer = vm.addr(i.deployerPk);

        vm.startBroadcast(i.deployerPk);
        v.strategyVaultMomentum =
            _deployBase(i, deployer, CLASS_MOM, PARAMS_HASH_MOM_BASE, "momentum_v1.base");
        v.strategyVaultMeanReversion =
            _deployBase(i, deployer, CLASS_MR, PARAMS_HASH_MR_BASE, "mean_reversion_v1.base");
        v.strategyVaultYieldRotation =
            _deployBase(i, deployer, CLASS_YR, PARAMS_HASH_YR_BASE, "yield_rotation_v1.base");

        MockERC20(i.usdc).approve(i.strategyRegistry, type(uint256).max);
        StrategyRegistry sr = StrategyRegistry(i.strategyRegistry);
        sr.registerStrategy(v.strategyVaultMomentum, CLASS_MOM, STRATEGY_STAKE);
        sr.registerStrategy(v.strategyVaultMeanReversion, CLASS_MR, STRATEGY_STAKE);
        sr.registerStrategy(v.strategyVaultYieldRotation, CLASS_YR, STRATEGY_STAKE);
        vm.stopBroadcast();

        _logAndPersist(v, i.outLabel);
    }

    function _deployBase(
        Inputs memory i,
        address deployer,
        bytes32 declaredClass,
        bytes32 paramsHash,
        string memory label
    ) internal returns (address) {
        StrategyVault impl = new StrategyVault(i.oraclePriceAnchor, i.oracleYieldAnchor);
        address[] memory universe = new address[](1);
        universe[0] = i.usdc;
        IStrategyVault.StrategyManifest memory m = IStrategyVault.StrategyManifest({
            declaredClass: declaredClass,
            assetUniverse: universe,
            maxCapacity: MAX_CAPACITY,
            feeRateBps: STRATEGY_FEE_BPS,
            operator: deployer,
            stakeAmount: STRATEGY_STAKE,
            paramsHash: paramsHash
        });
        StrategyVault.InitParams memory p = StrategyVault.InitParams({
            manifest: m,
            baseAsset: MockERC20(i.usdc),
            registry: i.strategyRegistry,
            verifier: i.tradeVerifier,
            allowedRouter: i.swapRouter,
            navOracle: deployer,
            allocatorVault: i.allocatorVault,
            priceAnchor: i.oraclePriceAnchor,
            yieldAnchor: i.oracleYieldAnchor,
            owner: deployer
        });
        bytes memory init = abi.encodeCall(StrategyVault.initialize, (p));
        address vault = address(new ERC1967Proxy(address(impl), init));
        console2.log(string.concat("StrategyVault[", label, "]:"), vault);
        return vault;
    }

    function _logAndPersist(BaseTrioAddresses memory v, string memory label) internal {
        console2.log("=== Helios Phase-3 base-trio redeployed ===");
        console2.log("StrategyVault[mom.base]: ", v.strategyVaultMomentum);
        console2.log("StrategyVault[mr.base]:  ", v.strategyVaultMeanReversion);
        console2.log("StrategyVault[yr.base]:  ", v.strategyVaultYieldRotation);

        string memory file = string.concat("./deployments/", label, ".json");
        _patchJson(file, v);
        console2.log("merged into:", file);
    }

    /// @dev Read existing addresses, copy every key forward EXCEPT the
    ///      three base-trio keys (which we overwrite with the new proxies),
    ///      then append the new base-trio keys. Top-level metadata
    ///      preserved; stamps `phase3BaseTrioRedeployedAt`.
    function _patchJson(string memory file, BaseTrioAddresses memory v) internal {
        string memory raw = vm.readFile(file);
        uint256 chainIdVal = vm.parseJsonUint(raw, ".chainId");
        uint256 deployedAtVal = vm.parseJsonUint(raw, ".deployedAt");

        string memory addrsBody = _existingAddresses(raw);
        addrsBody = string.concat(addrsBody, _baseTrioAddresses(v));

        string memory merged = string.concat(
            "{\n",
            '  "chainId": ',
            vm.toString(chainIdVal),
            ",\n",
            '  "deployedAt": ',
            vm.toString(deployedAtVal),
            ',\n  "phase": "3",\n',
            '  "phase3BaseTrioRedeployedAt": ',
            vm.toString(block.timestamp),
            ',\n  "addresses": {\n',
            addrsBody,
            "  }\n}\n"
        );
        vm.writeFile(file, merged);
    }

    function _existingAddresses(string memory raw) internal pure returns (string memory body) {
        string[] memory keys = vm.parseJsonKeys(raw, ".addresses");
        for (uint256 i = 0; i < keys.length; i++) {
            string memory k = keys[i];
            if (_isBaseTrioKey(k)) continue;
            address val = vm.parseJsonAddress(raw, string.concat(".addresses.", k));
            body = string.concat(body, _kv(k, val));
        }
    }

    function _baseTrioAddresses(BaseTrioAddresses memory v) internal pure returns (string memory) {
        return string.concat(
            _kv("strategyVaultMomentum", v.strategyVaultMomentum),
            _kv("strategyVaultMeanReversion", v.strategyVaultMeanReversion),
            _kvLast("strategyVaultYieldRotation", v.strategyVaultYieldRotation)
        );
    }

    function _isBaseTrioKey(string memory k) internal pure returns (bool) {
        bytes32 h = keccak256(bytes(k));
        return h == keccak256("strategyVaultMomentum")
            || h == keccak256("strategyVaultMeanReversion")
            || h == keccak256("strategyVaultYieldRotation");
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
