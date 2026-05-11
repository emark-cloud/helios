// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";
import { ERC1967Proxy } from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";

import { StrategyVault } from "src/StrategyVault.sol";
import { StrategyRegistry } from "src/StrategyRegistry.sol";
import { IStrategyVault } from "src/interfaces/IStrategyVault.sol";
import { MockERC20 } from "test/mocks/MockERC20.sol";

/// @notice Redeploy the three Phase-6 *base* vaults with dedicated
///         operator + navOracle keys per class so the strategy
///         services no longer share a nonce queue with the oracle
///         keeper. `_manifest.operator` is immutable post-init and
///         the contract has no setter, so a redeploy is the only
///         option (Helios.md §17 Phase 1; see `docs/phase6-plan.md`
///         WS9 for the nonce-contention root-cause).
///
/// New vaults are dual-registered in `StrategyRegistry` (V1, the
/// AllocatorVault's immutable reference) and `StrategyRegistryV2`
/// (which has `paramsHashOf` for `executeWithProof`). The previous
/// base vaults are left in place for now — capital migration is a
/// follow-up via Sentinel reconciliation; deactivation lands once
/// the new vaults take over allocations.
///
/// Variant 2/3 vaults are untouched (out of scope; the runtime is
/// single-vault per service container — see WS9 future-work). yr.base
/// is also untouched because the YR runtime stays disabled on Kite
/// (yield venues live on Arbitrum per Helios.md §12.1).
contract RedeployBaseVaultsWithOperators is Script {
    bytes32 internal constant CLASS_MOM =
        0x2a9aa442064b635baec37a7a259282faa5563a653a8325378d5676c6f04bc9dd;
    bytes32 internal constant CLASS_MR =
        0x18602f4f74172d545f5258541634e1a125c3a4e1227ee2a4cbee957d3490f1fb;

    bytes32 internal constant PH_MOM = keccak256("helios.momentum_v1.phase6.multiasset.base");
    bytes32 internal constant PH_MR = keccak256("helios.mean_reversion_v1.phase6.multiasset.base");

    uint256 internal constant MAX_CAPACITY = 1_000_000e18;
    uint256 internal constant STRATEGY_STAKE = 5000e18;
    uint16 internal constant STRATEGY_FEE_BPS = 2000;

    struct Env {
        address impl;
        address registryV1;
        address registryV2;
        address allocatorVault;
        address tradeVerifier;
        address swapRouter;
        address priceAnchor;
        address yieldAnchor;
        address usdc;
        address momOperator;
        address mrOperator;
        address[] universe;
        uint256 pk;
        address deployer;
    }

    function run() external {
        Env memory env = _readEnv();

        vm.startBroadcast(env.pk);
        _ensureStake(env);
        (address momVault, address mrVault) = _deployBoth(env);
        _registerBoth(env, momVault, mrVault);
        vm.stopBroadcast();

        console2.log("=== Dedicated-operator base vaults ===");
        console2.log("mom.base.dedicated  ", momVault, "operator", env.momOperator);
        console2.log("mr.base.dedicated   ", mrVault, "operator", env.mrOperator);
    }

    function _readEnv() internal view returns (Env memory env) {
        env.impl = vm.envAddress("STRATEGY_VAULT_IMPL");
        // Use distinct names so /srv/helios/.env's `STRATEGY_REGISTRY=V2`
        // (set after WS9 cutover) doesn't shadow this script's V1 reference.
        env.registryV1 = vm.envAddress("STRATEGY_REGISTRY_V1");
        env.registryV2 = vm.envAddress("STRATEGY_REGISTRY_V2");
        env.allocatorVault = vm.envAddress("ALLOCATOR_VAULT");
        env.tradeVerifier = vm.envAddress("TRADE_ATTESTATION_VERIFIER");
        env.swapRouter = vm.envAddress("SWAP_ROUTER");
        env.priceAnchor = vm.envAddress("ORACLE_PRICE_ANCHOR");
        env.yieldAnchor = vm.envAddress("ORACLE_YIELD_ANCHOR");
        env.usdc = vm.envAddress("USDC");
        env.momOperator = vm.envAddress("MOM_OPERATOR");
        env.mrOperator = vm.envAddress("MR_OPERATOR");

        address[] memory universe = new address[](4);
        universe[0] = env.usdc;
        universe[1] = vm.envAddress("MWBTC");
        universe[2] = vm.envAddress("MWETH");
        universe[3] = vm.envAddress("MSOL");
        env.universe = universe;

        env.pk = vm.envUint("DEPLOYER_PK");
        env.deployer = vm.addr(env.pk);
    }

    function _ensureStake(Env memory env) internal {
        // Make sure the deployer holds enough mUSDC to fund both stakes.
        // mUSDC is permissionless-mintable on testnet (`test/mocks/MockERC20.sol`).
        uint256 needed = 2 * STRATEGY_STAKE;
        uint256 have = MockERC20(env.usdc).balanceOf(env.deployer);
        if (have < needed) {
            MockERC20(env.usdc).mint(env.deployer, needed - have);
        }

        // Pre-approve both registries so each `registerStrategy`
        // can pull the stake.
        MockERC20(env.usdc).approve(env.registryV1, type(uint256).max);
        MockERC20(env.usdc).approve(env.registryV2, type(uint256).max);
    }

    function _deployBoth(Env memory env) internal returns (address momVault, address mrVault) {
        momVault = _deployVault(env, env.momOperator, CLASS_MOM, PH_MOM, "mom.base.dedicated");
        mrVault = _deployVault(env, env.mrOperator, CLASS_MR, PH_MR, "mr.base.dedicated");
    }

    function _registerBoth(Env memory env, address momVault, address mrVault) internal {
        // Dual-register: V1 keeps AllocatorVault's `isActive(...)` happy;
        // V2 holds `paramsHashOf` for `executeWithProof._activeParamsHash`.
        StrategyRegistry(env.registryV1).registerStrategy(momVault, CLASS_MOM, STRATEGY_STAKE);
        StrategyRegistry(env.registryV2).registerStrategy(momVault, CLASS_MOM, STRATEGY_STAKE);
        StrategyRegistry(env.registryV1).registerStrategy(mrVault, CLASS_MR, STRATEGY_STAKE);
        StrategyRegistry(env.registryV2).registerStrategy(mrVault, CLASS_MR, STRATEGY_STAKE);
    }

    function _deployVault(
        Env memory env,
        address operator,
        bytes32 declaredClass,
        bytes32 paramsHash,
        string memory label
    ) internal returns (address) {
        IStrategyVault.StrategyManifest memory m =
            IStrategyVault.StrategyManifest({
                declaredClass: declaredClass,
                assetUniverse: env.universe,
                maxCapacity: MAX_CAPACITY,
                feeRateBps: STRATEGY_FEE_BPS,
                operator: operator,
                stakeAmount: STRATEGY_STAKE,
                paramsHash: paramsHash
            });
        StrategyVault.InitParams memory p = StrategyVault.InitParams({
            manifest: m,
            baseAsset: MockERC20(env.usdc),
            registry: env.registryV2,
            verifier: env.tradeVerifier,
            allowedRouter: env.swapRouter,
            navOracle: operator,
            allocatorVault: env.allocatorVault,
            priceAnchor: env.priceAnchor,
            yieldAnchor: env.yieldAnchor,
            owner: env.deployer
        });
        bytes memory init = abi.encodeCall(StrategyVault.initialize, (p));
        address vault = address(new ERC1967Proxy(env.impl, init));
        console2.log(string.concat("StrategyVault[", label, "]:"), vault);
        return vault;
    }
}
