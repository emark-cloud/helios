// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";
import { ERC1967Proxy } from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";

import { StrategyRegistry } from "../src/StrategyRegistry.sol";
import { StrategyVault } from "../src/StrategyVault.sol";
import { IStrategyVault } from "../src/interfaces/IStrategyVault.sol";
import { MockERC20 } from "../test/mocks/MockERC20.sol";

/// @notice WS2.B — register a SECOND strategy vault per declared class so
///         the §8.2 reputation engine can compute cohort-relative scores
///         (cohort math requires `min_cohort_size = 2` per class). Phase 1
///         deployed exactly one vault per class; this script layers a
///         distinct second vault per class on top, with a non-zero
///         `paramsHash` that differs from the operator's primary strategy.
///
///         The second strategy is intentionally a *different operator
///         configuration*, not a clone — different `n_sigma_x100` for MR,
///         different `signal_threshold_bps` for momentum, different
///         `bridging_cost_bps` for YR. The `paramsHash` slot binds the
///         on-chain manifest to that config so the cohort splits cleanly.
///
///         What this script does NOT do: it does NOT swap in real
///         Groth16 verifiers (that's `DeployPhase2.s.sol`), it does NOT
///         touch the allocator surface, and it does NOT redeploy any
///         existing vaults.
///
///         Required env:
///           - DEPLOYER_PK
///           - USDC                (address; matches Phase-1 deploy)
///           - STRATEGY_REGISTRY
///           - ALLOCATOR_VAULT
///           - TRADE_VERIFIER
///           - SWAP_ROUTER         (mock router; YR vault ignores)
///         Optional env:
///           - OUT_LABEL           (default: chain name)
///
///         Inputs are also exposed via `runWith(Inputs)` for Foundry tests
///         that need to bypass `vm.envAddress` (parallel workers cannot
///         serialize the env map between threads).
contract RegisterPhase2Strategies is Script {
    bytes32 internal constant CLASS_MOM = keccak256("momentum_v1");
    bytes32 internal constant CLASS_MR = keccak256("mean_reversion_v1");
    bytes32 internal constant CLASS_YR = keccak256("yield_rotation_v1");

    uint16 internal constant STRATEGY_FEE_BPS = 1500; // 15% — tighter than primary's 10%
    uint256 internal constant STRATEGY_STAKE_2 = 5000e6; // 5k USDC
    uint256 internal constant MAX_CAPACITY = 1_000_000e6;

    /// @dev Distinct paramsHash per second-strategy variant. These are
    ///      Poseidon-style placeholders — the strategy SDK will replace
    ///      them with the operator's actual params commitment before the
    ///      first `executeWithProof`. Until then they only need to be
    ///      *different* from the primary strategy's hash (which Phase-1
    ///      sets to zero, so any non-zero value satisfies the cohort
    ///      diversity invariant).
    bytes32 internal constant PARAMS_HASH_MOM_V2 = keccak256("helios.mom_v1.variant2.signal_threshold_300");
    bytes32 internal constant PARAMS_HASH_MR_V2 = keccak256("helios.mr_v1.variant2.n_sigma_300");
    bytes32 internal constant PARAMS_HASH_YR_V2 = keccak256("helios.yr_v1.variant2.bridging_cost_60");

    struct Inputs {
        uint256 deployerPk;
        address usdc;
        address strategyRegistry;
        address allocatorVault;
        address tradeVerifier;
        address swapRouter;
        string outLabel;
    }

    struct Variant2Addresses {
        address strategyVaultMomentumVariant2;
        address strategyVaultMeanReversionVariant2;
        address strategyVaultYieldRotationVariant2;
    }

    function run() external returns (Variant2Addresses memory v) {
        uint256 pk = vm.envUint("DEPLOYER_PK");
        Inputs memory i = Inputs({
            deployerPk: pk,
            usdc: vm.envAddress("USDC"),
            strategyRegistry: vm.envAddress("STRATEGY_REGISTRY"),
            allocatorVault: vm.envAddress("ALLOCATOR_VAULT"),
            tradeVerifier: vm.envAddress("TRADE_VERIFIER"),
            swapRouter: vm.envAddress("SWAP_ROUTER"),
            outLabel: vm.envOr("OUT_LABEL", _chainName())
        });
        return runWith(i);
    }

    function runWith(Inputs memory i) public returns (Variant2Addresses memory v) {
        address deployer = vm.addr(i.deployerPk);

        vm.startBroadcast(i.deployerPk);
        v.strategyVaultMomentumVariant2 = _deployVariant(
            i, deployer, CLASS_MOM, PARAMS_HASH_MOM_V2, "momentum_v1.variant2"
        );
        v.strategyVaultMeanReversionVariant2 = _deployVariant(
            i, deployer, CLASS_MR, PARAMS_HASH_MR_V2, "mean_reversion_v1.variant2"
        );
        v.strategyVaultYieldRotationVariant2 = _deployVariant(
            i, deployer, CLASS_YR, PARAMS_HASH_YR_V2, "yield_rotation_v1.variant2"
        );

        MockERC20(i.usdc).approve(i.strategyRegistry, type(uint256).max);
        StrategyRegistry sr = StrategyRegistry(i.strategyRegistry);
        sr.registerStrategy(v.strategyVaultMomentumVariant2, CLASS_MOM, STRATEGY_STAKE_2);
        sr.registerStrategy(v.strategyVaultMeanReversionVariant2, CLASS_MR, STRATEGY_STAKE_2);
        sr.registerStrategy(v.strategyVaultYieldRotationVariant2, CLASS_YR, STRATEGY_STAKE_2);
        vm.stopBroadcast();

        _logAndPersist(v, i.outLabel);
    }

    function _deployVariant(
        Inputs memory i,
        address deployer,
        bytes32 declaredClass,
        bytes32 paramsHash,
        string memory label
    ) internal returns (address) {
        StrategyVault impl = new StrategyVault();
        address[] memory universe = new address[](1);
        universe[0] = i.usdc;
        IStrategyVault.StrategyManifest memory m = IStrategyVault.StrategyManifest({
            declaredClass: declaredClass,
            assetUniverse: universe,
            maxCapacity: MAX_CAPACITY,
            feeRateBps: STRATEGY_FEE_BPS,
            operator: deployer,
            stakeAmount: STRATEGY_STAKE_2,
            paramsHash: paramsHash
        });
        bytes memory init = abi.encodeCall(
            StrategyVault.initialize,
            (
                m,
                MockERC20(i.usdc),
                i.strategyRegistry,
                i.tradeVerifier,
                i.swapRouter,
                deployer,
                i.allocatorVault,
                deployer
            )
        );
        address vault = address(new ERC1967Proxy(address(impl), init));
        console2.log(string.concat("StrategyVault[", label, "]:"), vault);
        return vault;
    }

    function _logAndPersist(Variant2Addresses memory v, string memory label) internal {
        console2.log("=== Helios WS2.B variant2 strategies registered ===");
        console2.log("StrategyVault[mom.v2]: ", v.strategyVaultMomentumVariant2);
        console2.log("StrategyVault[mr.v2]:  ", v.strategyVaultMeanReversionVariant2);
        console2.log("StrategyVault[yr.v2]:  ", v.strategyVaultYieldRotationVariant2);

        string memory file = string.concat("./deployments/", label, ".json");
        _patchJson(file, v);
        console2.log("merged into:", file);
    }

    /// @dev Same merge strategy as `DeployPhase2._patchJson` — read the
    ///      existing addresses, copy every key forward, append the three
    ///      new variant2 keys. Top-level metadata (`chainId`, `deployedAt`,
    ///      `phase`, `phase2DeployedAt`) is preserved; we additionally
    ///      stamp `phase2BVariant2DeployedAt`.
    function _patchJson(string memory file, Variant2Addresses memory v) internal {
        string memory raw = vm.readFile(file);
        uint256 chainIdVal = vm.parseJsonUint(raw, ".chainId");
        uint256 deployedAtVal = vm.parseJsonUint(raw, ".deployedAt");

        string memory addrsBody = _existingAddresses(raw);
        addrsBody = string.concat(addrsBody, _variant2Addresses(v));

        string memory merged = string.concat(
            "{\n",
            '  "chainId": ',
            vm.toString(chainIdVal),
            ",\n",
            '  "deployedAt": ',
            vm.toString(deployedAtVal),
            ',\n  "phase": "2",\n',
            '  "phase2BVariant2DeployedAt": ',
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
            if (_isVariant2Key(k)) continue;
            address val = vm.parseJsonAddress(raw, string.concat(".addresses.", k));
            body = string.concat(body, _kv(k, val));
        }
    }

    function _variant2Addresses(Variant2Addresses memory v) internal pure returns (string memory) {
        return string.concat(
            _kv("strategyVaultMomentumVariant2", v.strategyVaultMomentumVariant2),
            _kv("strategyVaultMeanReversionVariant2", v.strategyVaultMeanReversionVariant2),
            _kvLast("strategyVaultYieldRotationVariant2", v.strategyVaultYieldRotationVariant2)
        );
    }

    function _isVariant2Key(string memory k) internal pure returns (bool) {
        bytes32 h = keccak256(bytes(k));
        return h == keccak256("strategyVaultMomentumVariant2")
            || h == keccak256("strategyVaultMeanReversionVariant2")
            || h == keccak256("strategyVaultYieldRotationVariant2");
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
