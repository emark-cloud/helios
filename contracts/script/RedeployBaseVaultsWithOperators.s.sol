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

    bytes32 internal constant PH_MOM =
        keccak256("helios.momentum_v1.phase6.multiasset.base");
    bytes32 internal constant PH_MR =
        keccak256("helios.mean_reversion_v1.phase6.multiasset.base");

    uint256 internal constant MAX_CAPACITY = 1_000_000e18;
    uint256 internal constant STRATEGY_STAKE = 5_000e18;
    uint16 internal constant STRATEGY_FEE_BPS = 2_000;

    function run() external {
        address impl = vm.envAddress("STRATEGY_VAULT_IMPL");
        address registryV1 = vm.envAddress("STRATEGY_REGISTRY");
        address registryV2 = vm.envAddress("STRATEGY_REGISTRY_V2");
        address allocatorVault = vm.envAddress("ALLOCATOR_VAULT");
        address tradeVerifier = vm.envAddress("TRADE_ATTESTATION_VERIFIER");
        address swapRouter = vm.envAddress("SWAP_ROUTER");
        address priceAnchor = vm.envAddress("ORACLE_PRICE_ANCHOR");
        address yieldAnchor = vm.envAddress("ORACLE_YIELD_ANCHOR");
        address usdc = vm.envAddress("USDC");
        address mWbtc = vm.envAddress("MWBTC");
        address mWeth = vm.envAddress("MWETH");
        address mSol = vm.envAddress("MSOL");

        address momOperator = vm.envAddress("MOM_OPERATOR");
        address mrOperator = vm.envAddress("MR_OPERATOR");

        uint256 pk = vm.envUint("DEPLOYER_PK");
        address deployer = vm.addr(pk);

        address[] memory universe = new address[](4);
        universe[0] = usdc;
        universe[1] = mWbtc;
        universe[2] = mWeth;
        universe[3] = mSol;

        vm.startBroadcast(pk);

        // Make sure the deployer holds enough mUSDC to fund both stakes.
        // mUSDC is permissionless-mintable on testnet (`test/mocks/MockERC20.sol`).
        uint256 needed = 2 * STRATEGY_STAKE;
        uint256 have = MockERC20(usdc).balanceOf(deployer);
        if (have < needed) {
            MockERC20(usdc).mint(deployer, needed - have);
        }

        // Pre-approve both registries so each `registerStrategy`
        // can pull the stake.
        MockERC20(usdc).approve(registryV1, type(uint256).max);
        MockERC20(usdc).approve(registryV2, type(uint256).max);

        address momVault = _deployVault(
            impl, deployer, momOperator, momOperator, usdc, registryV2,
            tradeVerifier, swapRouter, allocatorVault, priceAnchor,
            yieldAnchor, CLASS_MOM, universe, PH_MOM, "mom.base.dedicated"
        );
        address mrVault = _deployVault(
            impl, deployer, mrOperator, mrOperator, usdc, registryV2,
            tradeVerifier, swapRouter, allocatorVault, priceAnchor,
            yieldAnchor, CLASS_MR, universe, PH_MR, "mr.base.dedicated"
        );

        // Dual-register: V1 keeps AllocatorVault's `isActive(...)` happy;
        // V2 holds `paramsHashOf` for `executeWithProof._activeParamsHash`.
        StrategyRegistry(registryV1).registerStrategy(momVault, CLASS_MOM, STRATEGY_STAKE);
        StrategyRegistry(registryV2).registerStrategy(momVault, CLASS_MOM, STRATEGY_STAKE);
        StrategyRegistry(registryV1).registerStrategy(mrVault, CLASS_MR, STRATEGY_STAKE);
        StrategyRegistry(registryV2).registerStrategy(mrVault, CLASS_MR, STRATEGY_STAKE);

        vm.stopBroadcast();

        console2.log("=== Dedicated-operator base vaults ===");
        console2.log("mom.base.dedicated  ", momVault, "operator", momOperator);
        console2.log("mr.base.dedicated   ", mrVault,  "operator", mrOperator);
    }

    function _deployVault(
        address impl,
        address deployer,
        address operator,
        address navOracle,
        address usdc,
        address registry,
        address tradeVerifier,
        address swapRouter,
        address allocatorVault,
        address priceAnchor,
        address yieldAnchor,
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
            operator: operator,
            stakeAmount: STRATEGY_STAKE,
            paramsHash: paramsHash
        });
        StrategyVault.InitParams memory p = StrategyVault.InitParams({
            manifest: m,
            baseAsset: MockERC20(usdc),
            registry: registry,
            verifier: tradeVerifier,
            allowedRouter: swapRouter,
            navOracle: navOracle,
            allocatorVault: allocatorVault,
            priceAnchor: priceAnchor,
            yieldAnchor: yieldAnchor,
            owner: deployer
        });
        bytes memory init = abi.encodeCall(StrategyVault.initialize, (p));
        address vault = address(new ERC1967Proxy(impl, init));
        console2.log(string.concat("StrategyVault[", label, "]:"), vault);
        return vault;
    }
}
