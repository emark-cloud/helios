// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";
import { ERC1967Proxy } from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";

import { StrategyRegistry } from "../src/StrategyRegistry.sol";
import { AllocatorRegistry } from "../src/AllocatorRegistry.sol";
import { ReputationAnchor } from "../src/ReputationAnchor.sol";
import { TradeAttestationVerifier } from "../src/TradeAttestationVerifier.sol";
import { StrategyVault } from "../src/StrategyVault.sol";
import { IStrategyVault } from "../src/interfaces/IStrategyVault.sol";
import { AllocatorVault } from "../src/AllocatorVault.sol";
import { UserVault } from "../src/UserVault.sol";
import { MockSwapRouter } from "../src/mocks/MockSwapRouter.sol";
import { MockERC20 } from "../test/mocks/MockERC20.sol";
import { MockGroth16Verifier } from "../test/mocks/MockGroth16Verifier.sol";

/// @notice Phase 1 end-to-end deploy. Bootstraps the full vertical slice
///         (registries → anchor → verifier → vaults → mock swap router) on
///         a single chain. Designed for Kite testnet but runs unchanged on
///         anvil and on any EVM-compatible chain that lacks Algebra.
///
///         What it does NOT do (Phase 1 scope):
///         - Real Groth16 verifiers (a MockGroth16Verifier(true) is registered
///           per declared class as a placeholder; swap in MomentumV1Verifier
///           etc. once WS2.A ships them).
///         - LayerZero OApp wiring (Phase 5).
///         - Real USDC: deploys a MockUSDC unless USDC_ADDRESS is provided.
///
///         Outputs an addresses bundle to deployments/<chain>-phase1.json.
contract DeployPhase1 is Script {
    bytes32 internal constant CLASS_MOM = keccak256("momentum_v1");
    bytes32 internal constant CLASS_MR = keccak256("mean_reversion_v1");
    bytes32 internal constant CLASS_YR = keccak256("yield_rotation_v1");

    uint16 internal constant ALLOCATOR_FEE_BPS = 500;
    uint16 internal constant STRATEGY_FEE_BPS = 1000;
    uint64 internal constant MAX_SESSION_TTL = 30 days;
    uint256 internal constant STAKE_COOLDOWN = 7 days;
    uint256 internal constant STRATEGY_STAKE = 5000e6; // 5k USDC
    uint256 internal constant ALLOCATOR_STAKE = 5000e6;
    uint256 internal constant MAX_CAPACITY = 1_000_000e6;

    struct Phase1Addresses {
        address usdc;
        address swapRouter;
        address reputationAnchor;
        address strategyRegistry;
        address allocatorRegistry;
        address tradeVerifier;
        address momentumVerifier;
        address meanReversionVerifier;
        address yieldRotationVerifier;
        address userVault;
        address allocatorVault;
        address strategyVaultMomentum;
        address strategyVaultMeanReversion;
        address strategyVaultYieldRotation;
    }

    function run() external returns (Phase1Addresses memory a) {
        uint256 pk = vm.envUint("DEPLOYER_PK");
        address deployer = vm.addr(pk);

        vm.startBroadcast(pk);
        _deployTokensAndRouter(a, deployer);
        _deployReputationAndRegistries(a, deployer);
        _deployVerifiers(a, deployer);
        _deployVaults(a, deployer);
        _registerStrategiesAndAllocator(a);
        vm.stopBroadcast();

        _logAndPersist(a);
    }

    function _deployTokensAndRouter(Phase1Addresses memory a, address deployer) internal {
        a.usdc = vm.envOr("USDC_ADDRESS", address(0));
        if (a.usdc == address(0)) {
            MockERC20 mockUsdc = new MockERC20("Helios Mock USDC", "mUSDC");
            mockUsdc.mint(deployer, 10_000_000e6);
            a.usdc = address(mockUsdc);
        }
        a.swapRouter = address(new MockSwapRouter(deployer));
    }

    function _deployReputationAndRegistries(Phase1Addresses memory a, address deployer) internal {
        ReputationAnchor anchor = new ReputationAnchor(deployer, address(0), deployer);
        a.reputationAnchor = address(anchor);

        a.strategyRegistry = address(
            new StrategyRegistry(MockERC20(a.usdc), address(anchor), deployer, STAKE_COOLDOWN)
        );
        a.allocatorRegistry = address(
            new AllocatorRegistry(MockERC20(a.usdc), address(anchor), deployer, STAKE_COOLDOWN)
        );
        anchor.setRegistries(a.strategyRegistry, a.allocatorRegistry);
    }

    function _deployVerifiers(Phase1Addresses memory a, address deployer) internal {
        TradeAttestationVerifier v = new TradeAttestationVerifier(deployer);
        a.tradeVerifier = address(v);

        a.momentumVerifier = address(new MockGroth16Verifier(true));
        a.meanReversionVerifier = address(new MockGroth16Verifier(true));
        a.yieldRotationVerifier = address(new MockGroth16Verifier(true));

        v.registerVerifier(CLASS_MOM, a.momentumVerifier);
        v.registerVerifier(CLASS_MR, a.meanReversionVerifier);
        v.registerVerifier(CLASS_YR, a.yieldRotationVerifier);
    }

    function _deployVaults(Phase1Addresses memory a, address deployer) internal {
        UserVault uvImpl = new UserVault();
        bytes memory uvInit =
            abi.encodeCall(UserVault.initialize, (MockERC20(a.usdc), MAX_SESSION_TTL, deployer));
        a.userVault = address(new ERC1967Proxy(address(uvImpl), uvInit));

        AllocatorVault avImpl = new AllocatorVault();
        bytes memory avInit = abi.encodeCall(
            AllocatorVault.initialize,
            (
                MockERC20(a.usdc),
                deployer,
                a.userVault,
                a.strategyRegistry,
                ALLOCATOR_FEE_BPS,
                deployer
            )
        );
        a.allocatorVault = address(new ERC1967Proxy(address(avImpl), avInit));

        a.strategyVaultMomentum = _deployStrategyVault(a, deployer, CLASS_MOM, "momentum_v1");
        a.strategyVaultMeanReversion =
            _deployStrategyVault(a, deployer, CLASS_MR, "mean_reversion_v1");
        a.strategyVaultYieldRotation =
            _deployStrategyVault(a, deployer, CLASS_YR, "yield_rotation_v1");
    }

    function _registerStrategiesAndAllocator(Phase1Addresses memory a) internal {
        MockERC20(a.usdc).approve(a.strategyRegistry, type(uint256).max);
        StrategyRegistry sr = StrategyRegistry(a.strategyRegistry);
        sr.registerStrategy(a.strategyVaultMomentum, CLASS_MOM, STRATEGY_STAKE);
        sr.registerStrategy(a.strategyVaultMeanReversion, CLASS_MR, STRATEGY_STAKE);
        sr.registerStrategy(a.strategyVaultYieldRotation, CLASS_YR, STRATEGY_STAKE);

        bytes32[] memory supported = new bytes32[](3);
        supported[0] = CLASS_MOM;
        supported[1] = CLASS_MR;
        supported[2] = CLASS_YR;
        MockERC20(a.usdc).approve(a.allocatorRegistry, type(uint256).max);
        AllocatorRegistry(a.allocatorRegistry)
            .registerAllocator(
                "Helios Sentinel-shadow", // reserved name "Helios Sentinel" is multi-sig only
                a.allocatorVault,
                keccak256("sentinel_v1_ranking"),
                supported,
                ALLOCATOR_FEE_BPS,
                ALLOCATOR_STAKE
            );
    }

    function _deployStrategyVault(
        Phase1Addresses memory a,
        address deployer,
        bytes32 declaredClass,
        string memory label
    ) internal returns (address) {
        StrategyVault impl = new StrategyVault();
        address[] memory universe = new address[](1);
        universe[0] = a.usdc;
        IStrategyVault.StrategyManifest memory m = IStrategyVault.StrategyManifest({
            declaredClass: declaredClass,
            assetUniverse: universe,
            maxCapacity: MAX_CAPACITY,
            feeRateBps: STRATEGY_FEE_BPS,
            operator: deployer,
            stakeAmount: STRATEGY_STAKE
        });
        bytes memory init = abi.encodeCall(
            StrategyVault.initialize,
            (
                m,
                MockERC20(a.usdc),
                a.strategyRegistry,
                a.tradeVerifier,
                a.swapRouter,
                deployer, // navOracle (deployer in Phase 1)
                a.allocatorVault,
                deployer
            )
        );
        address vault = address(new ERC1967Proxy(address(impl), init));
        console2.log(string.concat("StrategyVault (", label, "):"), vault);
        return vault;
    }

    function _logAndPersist(Phase1Addresses memory a) internal {
        _logAddresses(a);
        string memory json = _buildJson(a);
        // Canonical path consumed by services (sentinel/momentum/reputation),
        // subgraph datasource rewrite, and frontend address loader.
        //
        // `OUT_LABEL` lets the local docker-compose anvil-kite run (chainid
        // 2368, mirrors Kite testnet) write to a *separate* file from a real
        // testnet broadcast — Track A sets `OUT_LABEL=anvil-kite`, Track B
        // leaves it unset and writes to `kite-testnet.json` (the file judges
        // / Goldsky read).
        string memory label = vm.envOr("OUT_LABEL", _chainName());
        string memory file = string.concat("./deployments/", label, ".json");
        vm.writeFile(file, json);
        console2.log("wrote:", file);
    }

    function _logAddresses(Phase1Addresses memory a) internal view {
        console2.log("=== Helios Phase 1 deploy ===");
        console2.log("chainId:                 ", block.chainid);
        console2.log("USDC:                    ", a.usdc);
        console2.log("MockSwapRouter:          ", a.swapRouter);
        console2.log("ReputationAnchor:        ", a.reputationAnchor);
        console2.log("StrategyRegistry:        ", a.strategyRegistry);
        console2.log("AllocatorRegistry:       ", a.allocatorRegistry);
        console2.log("TradeAttestationVerifier:", a.tradeVerifier);
        console2.log("UserVault:               ", a.userVault);
        console2.log("AllocatorVault:          ", a.allocatorVault);
        console2.log("StrategyVault[mom]:      ", a.strategyVaultMomentum);
        console2.log("StrategyVault[mr]:       ", a.strategyVaultMeanReversion);
        console2.log("StrategyVault[yr]:       ", a.strategyVaultYieldRotation);
    }

    function _buildJson(Phase1Addresses memory a) internal view returns (string memory) {
        return string.concat(_jsonHeader(), _jsonInfra(a), _jsonVaults(a), "  }\n}\n");
    }

    function _jsonInfra(Phase1Addresses memory a) internal pure returns (string memory) {
        return string.concat(
            _kv("usdc", a.usdc, true),
            _kv("swapRouter", a.swapRouter, true),
            _kv("reputationAnchor", a.reputationAnchor, true),
            _kv("strategyRegistry", a.strategyRegistry, true),
            _kv("allocatorRegistry", a.allocatorRegistry, true),
            _kv("tradeAttestationVerifier", a.tradeVerifier, true),
            _jsonVerifiers(a)
        );
    }

    function _jsonVaults(Phase1Addresses memory a) internal pure returns (string memory) {
        return string.concat(
            _kv("userVault", a.userVault, true),
            _kv("allocatorVault", a.allocatorVault, true),
            _kv("strategyVaultMomentum", a.strategyVaultMomentum, true),
            _kv("strategyVaultMeanReversion", a.strategyVaultMeanReversion, true),
            _kv("strategyVaultYieldRotation", a.strategyVaultYieldRotation, false)
        );
    }

    function _jsonHeader() internal view returns (string memory) {
        return string.concat(
            "{\n",
            '  "chainId": ',
            vm.toString(block.chainid),
            ',\n  "deployedAt": ',
            vm.toString(block.timestamp),
            ',\n  "phase": "1",\n',
            '  "addresses": {\n'
        );
    }

    function _jsonVerifiers(Phase1Addresses memory a) internal pure returns (string memory) {
        return string.concat(
            _kv("momentumVerifier", a.momentumVerifier, true),
            _kv("meanReversionVerifier", a.meanReversionVerifier, true),
            _kv("yieldRotationVerifier", a.yieldRotationVerifier, true)
        );
    }

    function _kv(string memory k, address v, bool comma) internal pure returns (string memory) {
        return string.concat('    "', k, '": "', _toChecksum(v), '"', comma ? ",\n" : "\n");
    }

    function _toChecksum(address a) internal pure returns (string memory) {
        // Foundry's vm.toString lowercase address format is fine for JSON.
        bytes memory raw = bytes(_addrLower(a));
        return string(raw);
    }

    function _addrLower(address a) internal pure returns (string memory) {
        bytes memory hexChars = "0123456789abcdef";
        bytes20 v = bytes20(a);
        bytes memory out = new bytes(42);
        out[0] = "0";
        out[1] = "x";
        for (uint256 i = 0; i < 20; i++) {
            out[2 + i * 2] = hexChars[uint8(v[i] >> 4)];
            out[3 + i * 2] = hexChars[uint8(v[i] & 0x0f)];
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
