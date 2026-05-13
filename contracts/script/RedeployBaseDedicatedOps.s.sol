// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";
import { ERC1967Proxy } from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";

import { StrategyRegistry } from "../src/StrategyRegistry.sol";
import { StrategyVault } from "../src/StrategyVault.sol";
import { IStrategyVault } from "../src/interfaces/IStrategyVault.sol";
import { MockERC20 } from "../test/mocks/MockERC20.sol";
import { ClassIds } from "../src/ClassIds.sol";
import { IERC20 } from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import { IERC20Metadata } from "@openzeppelin/contracts/token/ERC20/extensions/IERC20Metadata.sol";

interface IStrategyVaultDeactivate {
    function totalNAV() external view returns (uint256);
}

/// @notice Redeploy Base mom + mr vaults with per-class dedicated
///         operator/navOracle EOAs so parallel NAV reporting on
///         Base-Sepolia doesn't hit shared-deployer nonce contention
///         (same mitigation as Kite WS9 #9 — see memory
///         `project_phase6_ws9_dedicated_keys`).
///
///         Replaces the morning mom.base/mr.base proxies. Old proxies
///         are deactivated via SR.deactivate() (operator-only, deployer
///         can sign since they were deployed with operator=deployer).
///         New proxies stake 5_000 mUSDC each.
///
///         Required env (all unprefixed for direct env-cast use):
///           - DEPLOYER_PK
///           - MOM_BASE_OPERATOR_PK   dedicated EOA owning mom.base
///           - MR_BASE_OPERATOR_PK    dedicated EOA owning mr.base
///           - STRATEGY_VAULT_IMPL    Base CXR-aware impl
///                                    `0x735680A32A0e5d9d23D7e8e8302F434e7F30428E`
///
///         Side-effect on `./deployments/base-sepolia.json`:
///           - addresses.phase6VaultMomentumBase (replaced)
///           - addresses.phase6VaultMeanReversionBase (replaced)
///           - addresses.phase6VaultMomentumBaseLegacy_morning_shared
///           - addresses.phase6VaultMeanReversionBaseLegacy_morning_shared
contract RedeployBaseDedicatedOps is Script {
    string internal constant FILE = "./deployments/base-sepolia.json";

    bytes32 internal constant CLASS_MOM = ClassIds.MOMENTUM_V1;
    bytes32 internal constant CLASS_MR = ClassIds.MEAN_REVERSION_V1;

    uint16 internal constant STRATEGY_FEE_BPS = 1500;
    uint256 internal constant STAKE_WHOLE = 5000;
    uint256 internal constant CAPACITY_WHOLE = 1_000_000;

    bytes32 internal constant PH_MOM_BASE =
        keccak256("helios.mom_v1.phase6.multiasset.base.remote.v2");
    bytes32 internal constant PH_MR_BASE =
        keccak256("helios.mean_rev_v1.phase6.multiasset.base.remote.v2");

    struct Inputs {
        uint256 deployerPk;
        address deployer;
        address momOp;
        address mrOp;
        address impl;
        address usdc;
        address registry;
        address verifier;
        address swapRouter;
        address priceAnchor;
        address yieldAnchor;
        address oldMom;
        address oldMr;
        uint256 stake;
        uint256 capacity;
    }

    function _loadInputs() internal view returns (Inputs memory i) {
        i.deployerPk = vm.envUint("DEPLOYER_PK");
        i.deployer = vm.addr(i.deployerPk);
        i.momOp = vm.addr(vm.envUint("MOM_BASE_OPERATOR_PK"));
        i.mrOp = vm.addr(vm.envUint("MR_BASE_OPERATOR_PK"));
        i.impl = vm.envAddress("STRATEGY_VAULT_IMPL");
        i.usdc = _readAddress(".addresses.usdc");
        i.registry = _readAddress(".addresses.strategyRegistry");
        i.verifier = _readAddress(".addresses.tradeAttestationVerifier");
        i.swapRouter = _readAddress(".addresses.swapRouter");
        i.priceAnchor = _readAddress(".addresses.oraclePriceAnchor");
        i.yieldAnchor = _readAddress(".addresses.oracleYieldAnchor");
        i.oldMom = _readAddress(".addresses.phase6VaultMomentumBase");
        i.oldMr = _readAddress(".addresses.phase6VaultMeanReversionBase");
        uint8 dec = IERC20Metadata(i.usdc).decimals();
        i.stake = STAKE_WHOLE * (10 ** dec);
        i.capacity = CAPACITY_WHOLE * (10 ** dec);
    }

    function run() external {
        require(block.chainid == 84_532, "RedeployBaseDedicatedOps: not Base-Sepolia");
        Inputs memory i = _loadInputs();
        require(i.impl != address(0), "impl missing");
        require(i.swapRouter != address(0), "swapRouter missing");

        vm.startBroadcast(i.deployerPk);
        _deactivateOldVaults(i);
        (address newMom, address newMr) = _deployBothVaults(i);
        IERC20(i.usdc).approve(i.registry, type(uint256).max);
        StrategyRegistry(i.registry).registerStrategy(newMom, CLASS_MOM, i.stake);
        StrategyRegistry(i.registry).registerStrategy(newMr, CLASS_MR, i.stake);
        console2.log("registered new mom.base + mr.base on Base SR");
        vm.stopBroadcast();

        _persistAddresses(i.oldMom, i.oldMr, newMom, newMr);
        console2.log("=== Base dedicated-ops redeploy ===");
        console2.log("new mom.base:", newMom);
        console2.log("new mr.base: ", newMr);
    }

    function _deactivateOldVaults(Inputs memory i) internal {
        if (i.oldMom != address(0) && IStrategyVaultDeactivate(i.oldMom).totalNAV() == 0) {
            StrategyRegistry(i.registry).deactivate(i.oldMom);
            console2.log("deactivated old mom.base:", i.oldMom);
        }
        if (i.oldMr != address(0) && IStrategyVaultDeactivate(i.oldMr).totalNAV() == 0) {
            StrategyRegistry(i.registry).deactivate(i.oldMr);
            console2.log("deactivated old mr.base:", i.oldMr);
        }
    }

    function _deployBothVaults(Inputs memory i) internal returns (address newMom, address newMr) {
        address[] memory universe = new address[](2);
        universe[0] = i.usdc;
        universe[1] = 0x4200000000000000000000000000000000000006; // WETH9 OP predeploy
        newMom = _deployVault(i, CLASS_MOM, universe, PH_MOM_BASE, "mom.base", i.momOp);
        newMr = _deployVault(i, CLASS_MR, universe, PH_MR_BASE, "mr.base", i.mrOp);
    }

    function _persistAddresses(address oldMom, address oldMr, address newMom, address newMr)
        internal
    {
        vm.writeJson(
            string.concat('"', vm.toString(oldMom), '"'),
            FILE,
            ".addresses.phase6VaultMomentumBaseLegacy_morning_shared"
        );
        vm.writeJson(
            string.concat('"', vm.toString(oldMr), '"'),
            FILE,
            ".addresses.phase6VaultMeanReversionBaseLegacy_morning_shared"
        );
        vm.writeJson(
            string.concat('"', vm.toString(newMom), '"'), FILE, ".addresses.phase6VaultMomentumBase"
        );
        vm.writeJson(
            string.concat('"', vm.toString(newMr), '"'),
            FILE,
            ".addresses.phase6VaultMeanReversionBase"
        );
    }

    function _deployVault(
        Inputs memory i,
        bytes32 declaredClass,
        address[] memory universe,
        bytes32 paramsHash,
        string memory label,
        address operator_
    ) internal returns (address vault) {
        IStrategyVault.StrategyManifest memory m = IStrategyVault.StrategyManifest({
            declaredClass: declaredClass,
            assetUniverse: universe,
            maxCapacity: i.capacity,
            feeRateBps: STRATEGY_FEE_BPS,
            operator: operator_,
            stakeAmount: i.stake,
            paramsHash: paramsHash
        });

        StrategyVault.InitParams memory p = StrategyVault.InitParams({
            manifest: m,
            baseAsset: MockERC20(i.usdc),
            registry: i.registry,
            verifier: i.verifier,
            allowedRouter: i.swapRouter,
            navOracle: operator_,
            allocatorVault: i.deployer,
            priceAnchor: i.priceAnchor,
            yieldAnchor: i.yieldAnchor,
            owner: i.deployer
        });

        vault = address(new ERC1967Proxy(i.impl, abi.encodeCall(StrategyVault.initialize, (p))));
        console2.log(string.concat("StrategyVault[", label, "] dedicated-ops:"), vault);
    }

    function _readAddress(string memory key) internal view returns (address) {
        string memory json = vm.readFile(FILE);
        bytes memory raw = vm.parseJson(json, key);
        if (raw.length == 0) return address(0);
        return abi.decode(raw, (address));
    }
}
