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

    function run() external {
        require(block.chainid == 84_532, "RedeployBaseDedicatedOps: not Base-Sepolia");

        uint256 deployerPk = vm.envUint("DEPLOYER_PK");
        address deployer = vm.addr(deployerPk);
        uint256 momOpPk = vm.envUint("MOM_BASE_OPERATOR_PK");
        uint256 mrOpPk = vm.envUint("MR_BASE_OPERATOR_PK");
        address momOp = vm.addr(momOpPk);
        address mrOp = vm.addr(mrOpPk);

        address impl = vm.envAddress("STRATEGY_VAULT_IMPL");
        address usdc = _readAddress(".addresses.usdc");
        address registry = _readAddress(".addresses.strategyRegistry");
        address verifier = _readAddress(".addresses.tradeAttestationVerifier");
        address swapRouter = _readAddress(".addresses.swapRouter");
        address priceAnchor = _readAddress(".addresses.oraclePriceAnchor");
        address yieldAnchor = _readAddress(".addresses.oracleYieldAnchor");
        address oldMom = _readAddress(".addresses.phase6VaultMomentumBase");
        address oldMr = _readAddress(".addresses.phase6VaultMeanReversionBase");

        require(impl != address(0), "impl missing");
        require(swapRouter != address(0), "swapRouter missing");

        uint8 dec = IERC20Metadata(usdc).decimals();
        uint256 stake = STAKE_WHOLE * (10 ** dec);
        uint256 capacity = CAPACITY_WHOLE * (10 ** dec);

        // 1. Deactivate old proxies (operator = deployer on the morning
        //    deploy). Skip if either holds NAV (none should at this stage).
        vm.startBroadcast(deployerPk);
        if (oldMom != address(0) && IStrategyVaultDeactivate(oldMom).totalNAV() == 0) {
            StrategyRegistry(registry).deactivate(oldMom);
            console2.log("deactivated old mom.base:", oldMom);
        }
        if (oldMr != address(0) && IStrategyVaultDeactivate(oldMr).totalNAV() == 0) {
            StrategyRegistry(registry).deactivate(oldMr);
            console2.log("deactivated old mr.base:", oldMr);
        }

        // 2. Deploy fresh proxies with dedicated operator/navOracle EOAs.
        address[] memory universe = new address[](2);
        universe[0] = usdc;
        universe[1] = 0x4200000000000000000000000000000000000006; // WETH9 OP predeploy

        address newMom = _deployVault(
            impl,
            CLASS_MOM,
            universe,
            PH_MOM_BASE,
            "mom.base",
            momOp,
            usdc,
            registry,
            verifier,
            swapRouter,
            priceAnchor,
            yieldAnchor,
            deployer,
            stake,
            capacity
        );
        address newMr = _deployVault(
            impl,
            CLASS_MR,
            universe,
            PH_MR_BASE,
            "mr.base",
            mrOp,
            usdc,
            registry,
            verifier,
            swapRouter,
            priceAnchor,
            yieldAnchor,
            deployer,
            stake,
            capacity
        );

        // 3. Register new vaults on SR (deployer pays stake; operator
        //    field on the SR entry mirrors the manifest operator).
        IERC20(usdc).approve(registry, type(uint256).max);
        StrategyRegistry(registry).registerStrategy(newMom, CLASS_MOM, stake);
        StrategyRegistry(registry).registerStrategy(newMr, CLASS_MR, stake);
        console2.log("registered new mom.base + mr.base on Base SR");
        vm.stopBroadcast();

        // 4. Persist addresses — keep the morning shared-deployer ones
        //    under *Legacy keys for audit history.
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

        console2.log("=== Base dedicated-ops redeploy ===");
        console2.log("mom.base operator:", momOp);
        console2.log("mr.base operator: ", mrOp);
        console2.log("new mom.base:", newMom);
        console2.log("new mr.base: ", newMr);
        console2.log("patched:", FILE);
    }

    function _deployVault(
        address impl,
        bytes32 declaredClass,
        address[] memory universe,
        bytes32 paramsHash,
        string memory label,
        address operator_,
        address usdc,
        address registry,
        address verifier,
        address swapRouter,
        address priceAnchor,
        address yieldAnchor,
        address allocatorVault_,
        uint256 stake,
        uint256 capacity
    ) internal returns (address vault) {
        IStrategyVault.StrategyManifest memory m =
            IStrategyVault.StrategyManifest({
                declaredClass: declaredClass,
                assetUniverse: universe,
                maxCapacity: capacity,
                feeRateBps: STRATEGY_FEE_BPS,
                operator: operator_,
                stakeAmount: stake,
                paramsHash: paramsHash
            });

        StrategyVault.InitParams memory p = StrategyVault.InitParams({
            manifest: m,
            baseAsset: MockERC20(usdc),
            registry: registry,
            verifier: verifier,
            allowedRouter: swapRouter,
            navOracle: operator_,
            allocatorVault: allocatorVault_,
            priceAnchor: priceAnchor,
            yieldAnchor: yieldAnchor,
            owner: allocatorVault_
        });

        vault = address(new ERC1967Proxy(impl, abi.encodeCall(StrategyVault.initialize, (p))));
        console2.log(string.concat("StrategyVault[", label, "] dedicated-ops:"), vault);
    }

    function _readAddress(string memory key) internal view returns (address) {
        string memory json = vm.readFile(FILE);
        bytes memory raw = vm.parseJson(json, key);
        if (raw.length == 0) return address(0);
        return abi.decode(raw, (address));
    }
}
