// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";
import { ERC1967Proxy } from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";

import { StrategyRegistry } from "../src/StrategyRegistry.sol";
import { StrategyVault } from "../src/StrategyVault.sol";
import { IStrategyVault } from "../src/interfaces/IStrategyVault.sol";
import { MockERC20 } from "../test/mocks/MockERC20.sol";
import { ClassIds } from "../src/ClassIds.sol";

/// @notice Phase-6 real-P&L workstream 1: redeploy nine StrategyVaults with
///         multi-asset universes so the testnet stack actually moves NAV
///         when prices move. Models on `RegisterFreshStrategy.s.sol` —
///         same JSON merge, same constructor wiring — but parameterized
///         over the (class, variant) cross-product and over the per-class
///         asset universe (mom/mr: [USDC, WBTC, WETH, SOL]; yr: [USDC]).
///
///         Reuses the existing Phase-6 impl when `STRATEGY_VAULT_IMPL` is
///         set; deploys a fresh impl otherwise so a forked dry-run works
///         without prior state.
///
///         Does NOT commit `paramsHash` — that's done off-chain by the
///         strategy SDK / e2e bring-up so the on-chain hash matches the
///         Poseidon-of-params the prover will witness against.
contract DeployPhase6MultiAssetVaults is Script {
    bytes32 internal constant CLASS_MOM = ClassIds.MOMENTUM_V1;
    bytes32 internal constant CLASS_MR = ClassIds.MEAN_REVERSION_V1;
    bytes32 internal constant CLASS_YR = ClassIds.YIELD_ROTATION_V1;

    uint16 internal constant STRATEGY_FEE_BPS = 1500;
    // mUSDC mock has 18 decimals (matches the Kite testnet ERC-20). The
    // earlier 6-dec values capped vault capacity at ~1e-6 mUSDC and
    // collapsed every Sentinel allocation with `CapacityExceeded()`.
    uint256 internal constant STRATEGY_STAKE = 5000e18;
    uint256 internal constant MAX_CAPACITY = 1_000_000e18;

    /// @dev Distinct paramsHash per (class, variant) so the cohort sees
    ///      nine separate strategies. Off-chain commit will replace
    ///      these with Poseidon-of-actual-params before the first trade.
    bytes32 internal constant PH_MOM_BASE = keccak256("helios.mom_v1.phase6.multiasset.base");
    bytes32 internal constant PH_MOM_V2 = keccak256("helios.mom_v1.phase6.multiasset.variant2");
    bytes32 internal constant PH_MOM_V3 = keccak256("helios.mom_v1.phase6.multiasset.variant3");
    bytes32 internal constant PH_MR_BASE = keccak256("helios.mean_rev_v1.phase6.multiasset.base");
    bytes32 internal constant PH_MR_V2 = keccak256("helios.mean_rev_v1.phase6.multiasset.variant2");
    bytes32 internal constant PH_MR_V3 = keccak256("helios.mean_rev_v1.phase6.multiasset.variant3");
    bytes32 internal constant PH_YR_BASE = keccak256("helios.yield_rot_v1.phase6.multiasset.base");
    bytes32 internal constant PH_YR_V2 =
        keccak256("helios.yield_rot_v1.phase6.multiasset.variant2");
    bytes32 internal constant PH_YR_V3 =
        keccak256("helios.yield_rot_v1.phase6.multiasset.variant3");

    /// @dev Bundle of inputs read from env / deployment JSON so the deploy
    ///      function signatures stay shallow (forge --via-ir keeps stack
    ///      depth in check).
    struct Inputs {
        uint256 deployerPk;
        address impl;
        address usdc;
        address wbtc;
        address weth;
        address sol;
        address strategyRegistry;
        address allocatorVault;
        address tradeVerifier;
        address swapRouter;
        address oraclePriceAnchor;
        address oracleYieldAnchor;
    }

    struct Vaults {
        address momentumBase;
        address momentumVariant2;
        address momentumVariant3;
        address meanReversionBase;
        address meanReversionVariant2;
        address meanReversionVariant3;
        address yieldRotationBase;
        address yieldRotationVariant2;
        address yieldRotationVariant3;
    }

    function run() external returns (Vaults memory v) {
        Inputs memory i = _loadInputs();
        address deployer = vm.addr(i.deployerPk);

        vm.startBroadcast(i.deployerPk);
        v = _deployAll(i, deployer);
        _registerAll(i, v);
        vm.stopBroadcast();

        _logAndPersist(v, vm.envOr("OUT_LABEL", _chainName()));
    }

    function _loadInputs() internal view returns (Inputs memory i) {
        i.deployerPk = vm.envUint("DEPLOYER_PK");
        i.impl = vm.envOr("STRATEGY_VAULT_IMPL", address(0));
        i.usdc = vm.envAddress("USDC");
        i.wbtc = vm.envAddress("MWBTC");
        i.weth = vm.envAddress("MWETH");
        i.sol = vm.envAddress("MSOL");
        i.strategyRegistry = vm.envAddress("STRATEGY_REGISTRY");
        i.allocatorVault = vm.envAddress("ALLOCATOR_VAULT");
        i.tradeVerifier = vm.envAddress("TRADE_VERIFIER");
        i.swapRouter = vm.envAddress("SWAP_ROUTER");
        i.oraclePriceAnchor = vm.envAddress("ORACLE_PRICE_ANCHOR");
        i.oracleYieldAnchor = vm.envAddress("ORACLE_YIELD_ANCHOR");
    }

    function _deployAll(Inputs memory i, address deployer) internal returns (Vaults memory v) {
        // If no pre-existing impl was supplied, deploy a fresh one so the
        // script also runs on a blank fork (forge dry-run). On real Kite
        // testnet broadcasts, STRATEGY_VAULT_IMPL points at the Phase-6
        // impl 0x934f7639… already on chain.
        if (i.impl == address(0)) {
            StrategyVault impl = new StrategyVault(i.oraclePriceAnchor, i.oracleYieldAnchor);
            i.impl = address(impl);
            console2.log("StrategyVault impl (fresh):", i.impl);
        } else {
            console2.log("StrategyVault impl (reused):", i.impl);
        }

        address[] memory spotUniverse = new address[](4);
        spotUniverse[0] = i.usdc;
        spotUniverse[1] = i.wbtc;
        spotUniverse[2] = i.weth;
        spotUniverse[3] = i.sol;

        address[] memory yrUniverse = new address[](1);
        yrUniverse[0] = i.usdc;

        v.momentumBase = _deployVault(i, deployer, CLASS_MOM, spotUniverse, PH_MOM_BASE, "mom.base");
        v.momentumVariant2 =
            _deployVault(i, deployer, CLASS_MOM, spotUniverse, PH_MOM_V2, "mom.variant2");
        v.momentumVariant3 =
            _deployVault(i, deployer, CLASS_MOM, spotUniverse, PH_MOM_V3, "mom.variant3");
        v.meanReversionBase =
            _deployVault(i, deployer, CLASS_MR, spotUniverse, PH_MR_BASE, "mr.base");
        v.meanReversionVariant2 =
            _deployVault(i, deployer, CLASS_MR, spotUniverse, PH_MR_V2, "mr.variant2");
        v.meanReversionVariant3 =
            _deployVault(i, deployer, CLASS_MR, spotUniverse, PH_MR_V3, "mr.variant3");
        v.yieldRotationBase = _deployVault(i, deployer, CLASS_YR, yrUniverse, PH_YR_BASE, "yr.base");
        v.yieldRotationVariant2 =
            _deployVault(i, deployer, CLASS_YR, yrUniverse, PH_YR_V2, "yr.variant2");
        v.yieldRotationVariant3 =
            _deployVault(i, deployer, CLASS_YR, yrUniverse, PH_YR_V3, "yr.variant3");
    }

    function _deployVault(
        Inputs memory i,
        address deployer,
        bytes32 declaredClass,
        address[] memory universe,
        bytes32 paramsHash,
        string memory label
    ) internal returns (address) {
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
        address vault = address(new ERC1967Proxy(i.impl, init));
        console2.log(string.concat("StrategyVault[", label, "]:"), vault);
        return vault;
    }

    function _registerAll(Inputs memory i, Vaults memory v) internal {
        // Top up approval — covers all nine registrations even if the
        // operator key was rotated since the last allowance was set.
        MockERC20(i.usdc).approve(i.strategyRegistry, type(uint256).max);

        StrategyRegistry r = StrategyRegistry(i.strategyRegistry);
        r.registerStrategy(v.momentumBase, CLASS_MOM, STRATEGY_STAKE);
        r.registerStrategy(v.momentumVariant2, CLASS_MOM, STRATEGY_STAKE);
        r.registerStrategy(v.momentumVariant3, CLASS_MOM, STRATEGY_STAKE);
        r.registerStrategy(v.meanReversionBase, CLASS_MR, STRATEGY_STAKE);
        r.registerStrategy(v.meanReversionVariant2, CLASS_MR, STRATEGY_STAKE);
        r.registerStrategy(v.meanReversionVariant3, CLASS_MR, STRATEGY_STAKE);
        r.registerStrategy(v.yieldRotationBase, CLASS_YR, STRATEGY_STAKE);
        r.registerStrategy(v.yieldRotationVariant2, CLASS_YR, STRATEGY_STAKE);
        r.registerStrategy(v.yieldRotationVariant3, CLASS_YR, STRATEGY_STAKE);
    }

    function _logAndPersist(Vaults memory v, string memory label) internal {
        console2.log("=== Helios Phase-6 multi-asset vaults ===");
        console2.log("mom.base:        ", v.momentumBase);
        console2.log("mom.variant2:    ", v.momentumVariant2);
        console2.log("mom.variant3:    ", v.momentumVariant3);
        console2.log("mr.base:         ", v.meanReversionBase);
        console2.log("mr.variant2:     ", v.meanReversionVariant2);
        console2.log("mr.variant3:     ", v.meanReversionVariant3);
        console2.log("yr.base:         ", v.yieldRotationBase);
        console2.log("yr.variant2:     ", v.yieldRotationVariant2);
        console2.log("yr.variant3:     ", v.yieldRotationVariant3);

        string memory file = string.concat("./deployments/", label, ".json");
        _patchJson(file, v);
        console2.log("merged into:", file);
    }

    /// @dev Read-merge-write the deployments JSON. The new `phase6Vault*`
    ///      keys live alongside the legacy `strategyVault*` entries —
    ///      block explorer continuity matters and downstream consumers
    ///      switch over by looking at `phase6Vault*` first.
    function _patchJson(string memory file, Vaults memory v) internal {
        string memory raw = vm.readFile(file);
        uint256 chainIdVal = vm.parseJsonUint(raw, ".chainId");
        uint256 deployedAtVal = vm.parseJsonUint(raw, ".deployedAt");

        string memory addrsBody = _existingAddresses(raw);
        addrsBody = string.concat(addrsBody, _kv("phase6VaultMomentum", v.momentumBase));
        addrsBody = string.concat(addrsBody, _kv("phase6VaultMomentumVariant2", v.momentumVariant2));
        addrsBody = string.concat(addrsBody, _kv("phase6VaultMomentumVariant3", v.momentumVariant3));
        addrsBody = string.concat(addrsBody, _kv("phase6VaultMeanReversion", v.meanReversionBase));
        addrsBody = string.concat(
            addrsBody, _kv("phase6VaultMeanReversionVariant2", v.meanReversionVariant2)
        );
        addrsBody = string.concat(
            addrsBody, _kv("phase6VaultMeanReversionVariant3", v.meanReversionVariant3)
        );
        addrsBody = string.concat(addrsBody, _kv("phase6VaultYieldRotation", v.yieldRotationBase));
        addrsBody = string.concat(
            addrsBody, _kv("phase6VaultYieldRotationVariant2", v.yieldRotationVariant2)
        );
        addrsBody = string.concat(
            addrsBody, _kvLast("phase6VaultYieldRotationVariant3", v.yieldRotationVariant3)
        );

        string memory merged = string.concat(
            "{\n",
            '  "chainId": ',
            vm.toString(chainIdVal),
            ",\n",
            '  "deployedAt": ',
            vm.toString(deployedAtVal),
            ',\n  "phase": "6",\n',
            '  "phase6MultiAssetVaultsDeployedAt": ',
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
            if (_isPhase6VaultKey(k)) continue; // dedupe on re-run
            address val = vm.parseJsonAddress(raw, string.concat(".addresses.", k));
            body = string.concat(body, _kv(k, val));
        }
    }

    function _isPhase6VaultKey(string memory k) internal pure returns (bool) {
        bytes32 h = keccak256(bytes(k));
        return h == keccak256("phase6VaultMomentum")
            || h == keccak256("phase6VaultMomentumVariant2")
            || h == keccak256("phase6VaultMomentumVariant3")
            || h == keccak256("phase6VaultMeanReversion")
            || h == keccak256("phase6VaultMeanReversionVariant2")
            || h == keccak256("phase6VaultMeanReversionVariant3")
            || h == keccak256("phase6VaultYieldRotation")
            || h == keccak256("phase6VaultYieldRotationVariant2")
            || h == keccak256("phase6VaultYieldRotationVariant3");
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
