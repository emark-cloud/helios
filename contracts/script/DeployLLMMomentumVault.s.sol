// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";
import { ERC1967Proxy } from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";

import { StrategyRegistry } from "../src/StrategyRegistry.sol";
import { StrategyVault } from "../src/StrategyVault.sol";
import { IStrategyVault } from "../src/interfaces/IStrategyVault.sol";
import { MockERC20 } from "../test/mocks/MockERC20.sol";
import { ClassIds } from "../src/ClassIds.sol";

/// @notice Deploy a single StrategyVault running the LLM-driven reference
///         strategy (`reference-strategies/llm_momentum_v1/`). The vault
///         declares class `MOMENTUM_V1` so it reuses the existing
///         momentum_v1 Groth16 verifier — only the signal source (Claude
///         via the Anthropic SDK) changes vs. the deterministic
///         momentum vaults.
///
///         Mirrors `DeployPhase6MultiAssetVaults.s.sol`:
///           - same impl (Phase-6 CXR-aware `STRATEGY_VAULT_IMPL`)
///           - same 4-asset spot universe `[USDC, WBTC, WETH, SOL]`
///           - same stake / capacity (5_000e18 / 1_000_000e18 mUSDC)
///           - dual-registered in V1 + V2 so AllocatorVault's active
///             check AND `StrategyVault._activeParamsHash` both resolve
///
///         Does NOT commit `paramsHash` on chain — the runtime
///         (`ensure_params_committed`) writes the Poseidon hash at first
///         boot. The placeholder hash here is keccak-of-tag and will be
///         overwritten before the first executeWithProof.
///
///         Requires dedicated operator + navOracle EOAs distinct from
///         the deployer (see `project_phase6_ws9_dedicated_keys` memory
///         on the shared-deployer nonce-contention issue).
///
/// Env vars (in addition to the standard Phase-6 set):
///   LLM_OPERATOR_ADDRESS   - EOA address that will sign executeWithProof
///   LLM_NAV_ORACLE_ADDRESS - EOA address that will sign NAV reports
contract DeployLLMMomentumVault is Script {
    bytes32 internal constant CLASS_MOM = ClassIds.MOMENTUM_V1;

    uint16 internal constant STRATEGY_FEE_BPS = 1500;
    uint256 internal constant STRATEGY_STAKE = 5000e18;
    uint256 internal constant MAX_CAPACITY = 1_000_000e18;

    /// @dev Placeholder paramsHash. Distinct from the existing Phase-6
    ///      mom variants so the LLM vault is a separate strategy in the
    ///      registry. Replaced by the runtime's Poseidon commit before
    ///      the first proof lands.
    bytes32 internal constant PH_LLM_MOM = keccak256("helios.momentum_v1.llm.v1");

    struct Inputs {
        uint256 deployerPk;
        address impl;
        address usdc;
        address wbtc;
        address weth;
        address sol;
        address strategyRegistry;
        address strategyRegistryV2;
        address allocatorVault;
        address tradeVerifier;
        address swapRouter;
        address oraclePriceAnchor;
        address oracleYieldAnchor;
        address operator;
        address navOracle;
    }

    function run() external returns (address vault) {
        Inputs memory i = _loadInputs();
        address deployer = vm.addr(i.deployerPk);

        vm.startBroadcast(i.deployerPk);
        vault = _deployVault(i, deployer);
        _registerVault(i, vault);
        vm.stopBroadcast();

        _logAndPersist(vault, vm.envOr("OUT_LABEL", _chainName()));
    }

    function _loadInputs() internal view returns (Inputs memory i) {
        i.deployerPk = vm.envUint("DEPLOYER_PK");
        // Reuse the existing Phase-6 CXR-aware impl on Kite testnet
        // (0xc3C7A30C…). If unset, deploy fresh — required for forked
        // dry-runs against a blank chain.
        i.impl = vm.envOr("STRATEGY_VAULT_IMPL", address(0));
        i.usdc = vm.envAddress("USDC");
        i.wbtc = vm.envAddress("MWBTC");
        i.weth = vm.envAddress("MWETH");
        i.sol = vm.envAddress("MSOL");
        i.strategyRegistry = vm.envAddress("STRATEGY_REGISTRY");
        i.strategyRegistryV2 = vm.envOr("STRATEGY_REGISTRY_V2", address(0));
        i.allocatorVault = vm.envAddress("ALLOCATOR_VAULT");
        i.tradeVerifier = vm.envAddress("TRADE_VERIFIER");
        i.swapRouter = vm.envAddress("SWAP_ROUTER");
        i.oraclePriceAnchor = vm.envAddress("ORACLE_PRICE_ANCHOR");
        i.oracleYieldAnchor = vm.envAddress("ORACLE_YIELD_ANCHOR");
        // Dedicated EOAs — must differ from deployer to avoid shared-nonce
        // contention with the other Phase-6 vaults (see WS9 #9 memory).
        i.operator = vm.envAddress("LLM_OPERATOR_ADDRESS");
        i.navOracle = vm.envAddress("LLM_NAV_ORACLE_ADDRESS");
        require(i.operator != vm.addr(i.deployerPk), "LLM_OPERATOR must differ from deployer");
        require(i.navOracle != vm.addr(i.deployerPk), "LLM_NAV_ORACLE must differ from deployer");
    }

    function _deployVault(Inputs memory i, address deployer) internal returns (address) {
        if (i.impl == address(0)) {
            StrategyVault impl = new StrategyVault(i.oraclePriceAnchor, i.oracleYieldAnchor);
            i.impl = address(impl);
            console2.log("StrategyVault impl (fresh):", i.impl);
        } else {
            console2.log("StrategyVault impl (reused):", i.impl);
        }

        address[] memory universe = new address[](4);
        universe[0] = i.usdc;
        universe[1] = i.wbtc;
        universe[2] = i.weth;
        universe[3] = i.sol;

        IStrategyVault.StrategyManifest memory m = IStrategyVault.StrategyManifest({
            declaredClass: CLASS_MOM,
            assetUniverse: universe,
            maxCapacity: MAX_CAPACITY,
            feeRateBps: STRATEGY_FEE_BPS,
            // Manifest operator = the dedicated LLM operator EOA. The
            // deployer remains owner of the proxy (UUPS upgrade rights);
            // the operator's only authority is `executeWithProof` calls.
            operator: i.operator,
            stakeAmount: STRATEGY_STAKE,
            paramsHash: PH_LLM_MOM
        });

        address vaultRegistry =
            i.strategyRegistryV2 == address(0) ? i.strategyRegistry : i.strategyRegistryV2;
        StrategyVault.InitParams memory p = StrategyVault.InitParams({
            manifest: m,
            baseAsset: MockERC20(i.usdc),
            registry: vaultRegistry,
            verifier: i.tradeVerifier,
            allowedRouter: i.swapRouter,
            navOracle: i.navOracle,
            allocatorVault: i.allocatorVault,
            priceAnchor: i.oraclePriceAnchor,
            yieldAnchor: i.oracleYieldAnchor,
            // Deployer keeps UUPS upgrade authority; not the LLM
            // operator (rotate to a dedicated multisig post-deploy if
            // upgrade authority needs to move).
            owner: deployer
        });
        bytes memory init = abi.encodeCall(StrategyVault.initialize, (p));
        address vault = address(new ERC1967Proxy(i.impl, init));
        console2.log("StrategyVault[llm.mom]:", vault);
        return vault;
    }

    function _registerVault(Inputs memory i, address vault) internal {
        // Approve both registries for the staking pull — dedupes the WS9
        // pattern so a single broadcast handles V1 + V2.
        MockERC20(i.usdc).approve(i.strategyRegistry, type(uint256).max);
        if (i.strategyRegistryV2 != address(0)) {
            MockERC20(i.usdc).approve(i.strategyRegistryV2, type(uint256).max);
        }

        StrategyRegistry(i.strategyRegistry).registerStrategy(vault, CLASS_MOM, STRATEGY_STAKE);
        if (i.strategyRegistryV2 != address(0)) {
            StrategyRegistry(i.strategyRegistryV2).registerStrategy(
                vault, CLASS_MOM, STRATEGY_STAKE
            );
        }
    }

    function _logAndPersist(address vault, string memory label) internal {
        console2.log("=== Helios LLM momentum vault ===");
        console2.log("phase6VaultLLMMomentum:", vault);

        string memory file = string.concat("./deployments/", label, ".json");
        _patchJson(file, vault);
        console2.log("merged into:", file);
    }

    /// @dev Read-merge-write the deployments JSON. Adds (or replaces)
    ///      the `phase6VaultLLMMomentum` key, preserving every existing
    ///      address entry so this script is safe to re-run.
    function _patchJson(string memory file, address vault) internal {
        string memory raw = vm.readFile(file);
        uint256 chainIdVal = vm.parseJsonUint(raw, ".chainId");
        uint256 deployedAtVal = vm.parseJsonUint(raw, ".deployedAt");

        string memory addrsBody = _existingAddresses(raw);
        addrsBody = string.concat(addrsBody, _kvLast("phase6VaultLLMMomentum", vault));

        string memory merged = string.concat(
            "{\n",
            '  "chainId": ',
            vm.toString(chainIdVal),
            ",\n",
            '  "deployedAt": ',
            vm.toString(deployedAtVal),
            ',\n  "phase": "6",\n',
            '  "phase6LLMMomentumDeployedAt": ',
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
            // Dedupe on re-run so a second invocation replaces the prior
            // address rather than appending a duplicate key.
            if (keccak256(bytes(k)) == keccak256("phase6VaultLLMMomentum")) continue;
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
