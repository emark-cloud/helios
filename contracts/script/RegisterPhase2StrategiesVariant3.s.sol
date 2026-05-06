// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";
import { ERC1967Proxy } from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";

import { StrategyRegistry } from "../src/StrategyRegistry.sol";
import { StrategyVault } from "../src/StrategyVault.sol";
import { IStrategyVault } from "../src/interfaces/IStrategyVault.sol";
import { MockERC20 } from "../test/mocks/MockERC20.sol";
import { ClassIds } from "../src/ClassIds.sol";

/// @notice Phase-2 testnet patch — register a THIRD strategy vault per
///         class on Kite testnet. Sibling to `RegisterPhase2Strategies.s.sol`,
///         which already deployed variant2 vaults under Poseidon class IDs.
///
///         Why: Phase-1 vaults on Kite testnet were registered against
///         keccak256-derived class IDs (deployed 2026-04-27, before the
///         Poseidon switch in `b24f183` on 2026-05-02). They're stranded
///         because the post-Phase-2 verifier registry only maps Poseidon
///         class IDs. RegisterPhase2Strategies brought one strategy per
///         Poseidon class online; this script brings the second so §8.2
///         cohort math (`min_cohort_size = 2`) holds for momentum / mean
///         reversion / yield rotation on testnet.
///
///         Mirrors the variant2 script verbatim except for:
///           - distinct paramsHash per class (`variant3`)
///           - distinct JSON output keys (`*Variant3`)
///           - distinct broadcast directory (this filename)
///
///         Required env: same as RegisterPhase2Strategies.s.sol
///         (DEPLOYER_PK, USDC, STRATEGY_REGISTRY, ALLOCATOR_VAULT,
///         TRADE_VERIFIER, SWAP_ROUTER, ORACLE_PRICE_ANCHOR,
///         ORACLE_YIELD_ANCHOR; optional OUT_LABEL).
contract RegisterPhase2StrategiesVariant3 is Script {
    bytes32 internal constant CLASS_MOM = ClassIds.MOMENTUM_V1;
    bytes32 internal constant CLASS_MR = ClassIds.MEAN_REVERSION_V1;
    bytes32 internal constant CLASS_YR = ClassIds.YIELD_ROTATION_V1;

    uint16 internal constant STRATEGY_FEE_BPS = 1200; // 12% — between primary's 10% and variant2's 15%
    uint256 internal constant STRATEGY_STAKE_3 = 5000e6; // 5k USDC
    uint256 internal constant MAX_CAPACITY = 1_000_000e6;

    bytes32 internal constant PARAMS_HASH_MOM_V3 =
        keccak256("helios.mom_v1.variant3.signal_threshold_400");
    bytes32 internal constant PARAMS_HASH_MR_V3 = keccak256("helios.mr_v1.variant3.n_sigma_250");
    bytes32 internal constant PARAMS_HASH_YR_V3 =
        keccak256("helios.yr_v1.variant3.bridging_cost_45");

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

    struct Variant3Addresses {
        address strategyVaultMomentumVariant3;
        address strategyVaultMeanReversionVariant3;
        address strategyVaultYieldRotationVariant3;
    }

    function run() external returns (Variant3Addresses memory v) {
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

    function runWith(Inputs memory i) public returns (Variant3Addresses memory v) {
        address deployer = vm.addr(i.deployerPk);

        vm.startBroadcast(i.deployerPk);
        v.strategyVaultMomentumVariant3 =
            _deployVariant(i, deployer, CLASS_MOM, PARAMS_HASH_MOM_V3, "momentum_v1.variant3");
        v.strategyVaultMeanReversionVariant3 =
            _deployVariant(i, deployer, CLASS_MR, PARAMS_HASH_MR_V3, "mean_reversion_v1.variant3");
        v.strategyVaultYieldRotationVariant3 =
            _deployVariant(i, deployer, CLASS_YR, PARAMS_HASH_YR_V3, "yield_rotation_v1.variant3");

        MockERC20(i.usdc).approve(i.strategyRegistry, type(uint256).max);
        StrategyRegistry sr = StrategyRegistry(i.strategyRegistry);
        sr.registerStrategy(v.strategyVaultMomentumVariant3, CLASS_MOM, STRATEGY_STAKE_3);
        sr.registerStrategy(v.strategyVaultMeanReversionVariant3, CLASS_MR, STRATEGY_STAKE_3);
        sr.registerStrategy(v.strategyVaultYieldRotationVariant3, CLASS_YR, STRATEGY_STAKE_3);
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
            stakeAmount: STRATEGY_STAKE_3,
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

    function _logAndPersist(Variant3Addresses memory v, string memory label) internal {
        console2.log("=== Helios variant3 strategies registered ===");
        console2.log("StrategyVault[mom.v3]: ", v.strategyVaultMomentumVariant3);
        console2.log("StrategyVault[mr.v3]:  ", v.strategyVaultMeanReversionVariant3);
        console2.log("StrategyVault[yr.v3]:  ", v.strategyVaultYieldRotationVariant3);

        string memory file = string.concat("./deployments/", label, ".json");
        _patchJson(file, v);
        console2.log("merged into:", file);
    }

    /// @dev Mirrors RegisterPhase2Strategies._patchJson: read the
    ///      existing addresses, copy every key forward (including the
    ///      variant2 keys), append the three new variant3 keys.
    function _patchJson(string memory file, Variant3Addresses memory v) internal {
        string memory raw = vm.readFile(file);
        uint256 chainIdVal = vm.parseJsonUint(raw, ".chainId");
        uint256 deployedAtVal = vm.parseJsonUint(raw, ".deployedAt");

        string memory addrsBody = _existingAddresses(raw);
        addrsBody = string.concat(addrsBody, _variant3Addresses(v));

        string memory merged = string.concat(
            "{\n",
            '  "chainId": ',
            vm.toString(chainIdVal),
            ",\n",
            '  "deployedAt": ',
            vm.toString(deployedAtVal),
            ',\n  "phase": "2",\n',
            '  "phase2BVariant3DeployedAt": ',
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
            if (_isVariant3Key(k)) continue;
            address val = vm.parseJsonAddress(raw, string.concat(".addresses.", k));
            body = string.concat(body, _kv(k, val));
        }
    }

    function _variant3Addresses(Variant3Addresses memory v) internal pure returns (string memory) {
        return string.concat(
            _kv("strategyVaultMomentumVariant3", v.strategyVaultMomentumVariant3),
            _kv("strategyVaultMeanReversionVariant3", v.strategyVaultMeanReversionVariant3),
            _kvLast("strategyVaultYieldRotationVariant3", v.strategyVaultYieldRotationVariant3)
        );
    }

    function _isVariant3Key(string memory k) internal pure returns (bool) {
        bytes32 h = keccak256(bytes(k));
        return h == keccak256("strategyVaultMomentumVariant3")
            || h == keccak256("strategyVaultMeanReversionVariant3")
            || h == keccak256("strategyVaultYieldRotationVariant3");
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
