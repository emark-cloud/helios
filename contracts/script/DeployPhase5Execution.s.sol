// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";

import { TradeAttestationVerifier } from "../src/TradeAttestationVerifier.sol";
import { MomentumV1Verifier } from "../src/verifiers/MomentumV1Verifier.sol";
import { MeanReversionV1Verifier } from "../src/verifiers/MeanReversionV1Verifier.sol";
import { YieldRotationV1Verifier } from "../src/verifiers/YieldRotationV1Verifier.sol";
import { MomentumV1VerifierAdapter } from "../src/verifiers/MomentumV1VerifierAdapter.sol";
import {
    MeanReversionV1VerifierAdapter
} from "../src/verifiers/MeanReversionV1VerifierAdapter.sol";
import {
    YieldRotationV1VerifierAdapter
} from "../src/verifiers/YieldRotationV1VerifierAdapter.sol";
import { OraclePriceAnchor } from "../src/OraclePriceAnchor.sol";
import { OracleYieldAnchor } from "../src/OracleYieldAnchor.sol";
import { HeliosOApp } from "../src/HeliosOApp.sol";
import { StrategyVault } from "../src/StrategyVault.sol";
import { MockUSDC } from "../src/mocks/MockUSDC.sol";
import { MockUniswapV3Router } from "../src/mocks/MockUniswapV3Router.sol";
import { MockYieldVault } from "../src/mocks/MockYieldVault.sol";
import { ClassIds } from "../src/ClassIds.sol";

/// @notice Phase-5 execution-chain deploy (Base Sepolia + Arbitrum Sepolia).
///
///         Branches on `block.chainid` to pick the right venue mix:
///           - Base Sepolia (84_532): records canonical Uniswap V3
///             SwapRouter02 under `swapRouter`, deploys `MockUniswapV3Router`
///             under `mockSwapRouter` for SDK fallback.
///           - Arbitrum Sepolia (421_614): records canonical Aave V3 Pool
///             under `aavePool`, deploys `MockYieldVault` under
///             `mockYieldVault` for SDK fallback.
///
///         Common surface: TAV + per-class verifier adapters,
///         OraclePriceAnchor + OracleYieldAnchor, HeliosOApp, MockUSDC OFT,
///         and one StrategyVault implementation contract per chain
///         (proxies + init are WS5 — local registry/allocator stubs land
///         alongside the executeWithProof attestation-forward hook).
///
///         Required env:
///           - DEPLOYER_PK
///           - LZ_ENDPOINT_BASE_SEPOLIA / LZ_ENDPOINT_ARBITRUM_SEPOLIA
///             (LZ V2 endpoint per chain; both are typically the same canonical
///             address `0x6EDCE65403992e310A62460808c4b910D972f10f`).
///           - LZ_KITE_EID (LZ V2 destination EID for Kite testnet)
///         Optional env:
///           - LZ_BASE_SEPOLIA_EID    (default 40_245)
///           - LZ_ARBITRUM_SEPOLIA_EID (default 40_231)
///           - UNISWAP_V3_ROUTER_BASE  (default 0x94cC0AaC535CCDB3C01d6787D6413C739ae12bc4)
///           - AAVE_V3_POOL_ARB        (default 0xBfC91D59fdAA134A4ED45f7B584cAf96D7792Eff)
///           - ORACLE_PRICE_SIGNER     (default deployer)
///           - ORACLE_YIELD_SIGNER     (default deployer)
///           - OUT_LABEL               (default chain name)
///
///         phase5-plan.md §WS2.
contract DeployPhase5Execution is Script {
    /// @dev Canonical Uniswap V3 SwapRouter02 deployment on Base Sepolia
    ///      (cross-referenced with Uniswap docs 2026-05-08).
    address internal constant UNISWAP_V3_ROUTER_BASE_SEPOLIA =
        0x94cC0AaC535CCDB3C01d6787D6413C739ae12bc4;

    /// @dev Canonical Aave V3 Pool on Arbitrum Sepolia (Aave docs 2026-05-08).
    address internal constant AAVE_V3_POOL_ARBITRUM_SEPOLIA =
        0xBfC91D59fdAA134A4ED45f7B584cAf96D7792Eff;

    /// @dev LayerZero V2 EID assignments (testnet).
    uint32 internal constant LZ_BASE_SEPOLIA_EID_DEFAULT = 40_245;
    uint32 internal constant LZ_ARBITRUM_SEPOLIA_EID_DEFAULT = 40_231;

    bytes32 internal constant CLASS_MOM = ClassIds.MOMENTUM_V1;
    bytes32 internal constant CLASS_MR = ClassIds.MEAN_REVERSION_V1;
    bytes32 internal constant CLASS_YR = ClassIds.YIELD_ROTATION_V1;

    struct Phase5Addresses {
        address mockUsdc;
        address heliosOApp;
        address tradeAttestationVerifier;
        address momentumVerifier;
        address momentumVerifierAdapter;
        address meanReversionVerifier;
        address meanReversionVerifierAdapter;
        address yieldRotationVerifier;
        address yieldRotationVerifierAdapter;
        address oraclePriceAnchor;
        address oracleYieldAnchor;
        address strategyVaultImpl;
        // Venue (real) — `swapRouter` on Base, `aavePool` on Arb.
        address venueReal;
        // Venue (mock) — `mockSwapRouter` on Base, `mockYieldVault` on Arb.
        address venueMock;
        // EIDs known at deploy time, persisted for the wire-peers script to consume.
        uint32 lzKiteEid;
        uint32 lzLocalEid;
    }

    function run() external returns (Phase5Addresses memory a) {
        uint256 pk = vm.envUint("DEPLOYER_PK");
        address deployer = vm.addr(pk);
        string memory label = vm.envOr("OUT_LABEL", _chainName());

        address lzEndpoint = _lzEndpoint();
        a.lzKiteEid = uint32(vm.envUint("LZ_KITE_EID"));
        a.lzLocalEid = _lzLocalEid();

        address priceSigner = vm.envOr("ORACLE_PRICE_SIGNER", deployer);
        address yieldSigner = vm.envOr("ORACLE_YIELD_SIGNER", deployer);

        vm.startBroadcast(pk);

        // 1. Tokens + venue
        a.mockUsdc = address(new MockUSDC(lzEndpoint, deployer));
        (a.venueReal, a.venueMock) = _deployVenue(deployer);

        // 2. HeliosOApp — execution chain ⇒ reputationAnchor=0
        a.heliosOApp = address(
            new HeliosOApp(
                lzEndpoint,
                deployer,
                a.lzKiteEid,
                address(0), // reputationAnchor: live only on Kite
                64 // maxPendingPerStrategy
            )
        );

        // 3. TAV + per-class verifiers + adapters
        TradeAttestationVerifier tav = new TradeAttestationVerifier(deployer);
        a.tradeAttestationVerifier = address(tav);

        MomentumV1Verifier momRaw = new MomentumV1Verifier();
        a.momentumVerifier = address(momRaw);
        a.momentumVerifierAdapter = address(new MomentumV1VerifierAdapter(address(momRaw)));

        MeanReversionV1Verifier mrRaw = new MeanReversionV1Verifier();
        a.meanReversionVerifier = address(mrRaw);
        a.meanReversionVerifierAdapter = address(new MeanReversionV1VerifierAdapter(address(mrRaw)));

        YieldRotationV1Verifier yrRaw = new YieldRotationV1Verifier();
        a.yieldRotationVerifier = address(yrRaw);
        a.yieldRotationVerifierAdapter = address(new YieldRotationV1VerifierAdapter(address(yrRaw)));

        tav.registerVerifier(CLASS_MOM, a.momentumVerifierAdapter);
        tav.registerVerifier(CLASS_MR, a.meanReversionVerifierAdapter);
        tav.registerVerifier(CLASS_YR, a.yieldRotationVerifierAdapter);

        // 4. Oracle anchors — local copies that the WS3 multi-chain poster
        //    targets each cycle. priceAnchor/yieldAnchor are baked into the
        //    StrategyVault impl as constructor immutables.
        a.oraclePriceAnchor = address(new OraclePriceAnchor(priceSigner, deployer));
        a.oracleYieldAnchor = address(new OracleYieldAnchor(yieldSigner, deployer));

        // 5. StrategyVault impl. Proxies + initialize() come in WS5 once
        //    the execution-chain registry/allocator-stub design lands.
        a.strategyVaultImpl = address(new StrategyVault(a.oraclePriceAnchor, a.oracleYieldAnchor));

        vm.stopBroadcast();

        _logAndPersist(a, label);
    }

    function _deployVenue(address deployer) internal returns (address realAddr, address mockAddr) {
        if (block.chainid == 84_532) {
            realAddr = vm.envOr("UNISWAP_V3_ROUTER_BASE", UNISWAP_V3_ROUTER_BASE_SEPOLIA);
            mockAddr = address(new MockUniswapV3Router(deployer));
        } else if (block.chainid == 421_614) {
            realAddr = vm.envOr("AAVE_V3_POOL_ARB", AAVE_V3_POOL_ARBITRUM_SEPOLIA);
            mockAddr = address(new MockYieldVault(deployer));
        } else {
            // Anvil / non-target chain: deploy both mocks so e2e can flip
            // the SDK between them without a chain-specific guard.
            realAddr = address(new MockUniswapV3Router(deployer));
            mockAddr = address(new MockYieldVault(deployer));
        }
    }

    function _lzEndpoint() internal view returns (address) {
        if (block.chainid == 84_532) {
            return vm.envAddress("LZ_ENDPOINT_BASE_SEPOLIA");
        } else if (block.chainid == 421_614) {
            return vm.envAddress("LZ_ENDPOINT_ARBITRUM_SEPOLIA");
        } else {
            return vm.envAddress("LZ_ENDPOINT");
        }
    }

    function _lzLocalEid() internal view returns (uint32) {
        if (block.chainid == 84_532) {
            return uint32(vm.envOr("LZ_BASE_SEPOLIA_EID", uint256(LZ_BASE_SEPOLIA_EID_DEFAULT)));
        } else if (block.chainid == 421_614) {
            return
                uint32(
                    vm.envOr("LZ_ARBITRUM_SEPOLIA_EID", uint256(LZ_ARBITRUM_SEPOLIA_EID_DEFAULT))
                );
        } else {
            return uint32(vm.envUint("LZ_LOCAL_EID"));
        }
    }

    function _chainName() internal view returns (string memory) {
        if (block.chainid == 2368) return "kite-testnet";
        if (block.chainid == 84_532) return "base-sepolia";
        if (block.chainid == 421_614) return "arbitrum-sepolia";
        if (block.chainid == 31_337) return "anvil";
        return vm.toString(block.chainid);
    }

    // ── Logging + JSON persistence ─────────────────────────────────

    function _logAndPersist(Phase5Addresses memory a, string memory label) internal {
        _logAddresses(a, label);
        string memory file = string.concat("./deployments/", label, ".json");
        vm.writeFile(file, _buildJson(a));
        console2.log("wrote:", file);
    }

    function _logAddresses(Phase5Addresses memory a, string memory label) internal view {
        console2.log("=== Helios Phase-5 execution deploy ===");
        console2.log("chain label:                   ", label);
        console2.log("chainId:                       ", block.chainid);
        console2.log("lz local EID:                  ", a.lzLocalEid);
        console2.log("lz Kite EID:                   ", a.lzKiteEid);
        console2.log("MockUSDC OFT:                  ", a.mockUsdc);
        console2.log("HeliosOApp:                    ", a.heliosOApp);
        console2.log("TAV:                           ", a.tradeAttestationVerifier);
        console2.log("MomentumV1Verifier:            ", a.momentumVerifier);
        console2.log("MomentumV1VerifierAdapter:     ", a.momentumVerifierAdapter);
        console2.log("MeanReversionV1Verifier:       ", a.meanReversionVerifier);
        console2.log("MeanReversionV1VerifierAdapter:", a.meanReversionVerifierAdapter);
        console2.log("YieldRotationV1Verifier:       ", a.yieldRotationVerifier);
        console2.log("YieldRotationV1VerifierAdapter:", a.yieldRotationVerifierAdapter);
        console2.log("OraclePriceAnchor:             ", a.oraclePriceAnchor);
        console2.log("OracleYieldAnchor:             ", a.oracleYieldAnchor);
        console2.log("StrategyVault impl:            ", a.strategyVaultImpl);
        console2.log("venue (real):                  ", a.venueReal);
        console2.log("venue (mock):                  ", a.venueMock);
    }

    function _buildJson(Phase5Addresses memory a) internal view returns (string memory) {
        return string.concat(_buildJsonHeader(a), _buildJsonAddresses(a), "  }\n}\n");
    }

    function _buildJsonHeader(Phase5Addresses memory a) internal view returns (string memory) {
        return string.concat(
            "{\n",
            '  "chainId": ',
            vm.toString(block.chainid),
            ",\n",
            '  "deployedAt": ',
            vm.toString(block.timestamp),
            ",\n",
            '  "phase": "5",\n',
            '  "phase5DeployedAt": ',
            vm.toString(block.timestamp),
            ",\n",
            '  "lzKiteEid": ',
            vm.toString(uint256(a.lzKiteEid)),
            ",\n",
            '  "lzLocalEid": ',
            vm.toString(uint256(a.lzLocalEid)),
            ',\n  "addresses": {\n'
        );
    }

    function _buildJsonAddresses(Phase5Addresses memory a) internal view returns (string memory) {
        return
            string.concat(_jsonCoreAddresses(a), _jsonVerifierAddresses(a), _jsonTailAddresses(a));
    }

    function _jsonCoreAddresses(Phase5Addresses memory a) internal pure returns (string memory) {
        return string.concat(
            _kv("usdc", a.mockUsdc),
            _kv("heliosOApp", a.heliosOApp),
            _kv("tradeAttestationVerifier", a.tradeAttestationVerifier)
        );
    }

    function _jsonVerifierAddresses(Phase5Addresses memory a)
        internal
        pure
        returns (string memory)
    {
        return string.concat(
            _kv("momentumVerifier", a.momentumVerifier),
            _kv("momentumVerifierAdapter", a.momentumVerifierAdapter),
            _kv("meanReversionVerifier", a.meanReversionVerifier),
            _kv("meanReversionVerifierAdapter", a.meanReversionVerifierAdapter),
            _kv("yieldRotationVerifier", a.yieldRotationVerifier),
            _kv("yieldRotationVerifierAdapter", a.yieldRotationVerifierAdapter)
        );
    }

    function _jsonTailAddresses(Phase5Addresses memory a) internal view returns (string memory) {
        (string memory venueRealKey, string memory venueMockKey) = _venueKeys();
        return string.concat(
            _kv("oraclePriceAnchor", a.oraclePriceAnchor),
            _kv("oracleYieldAnchor", a.oracleYieldAnchor),
            _kv("strategyVaultImpl", a.strategyVaultImpl),
            _kv(venueRealKey, a.venueReal),
            _kvLast(venueMockKey, a.venueMock)
        );
    }

    function _venueKeys() internal view returns (string memory realKey, string memory mockKey) {
        if (block.chainid == 84_532) {
            return ("swapRouter", "mockSwapRouter");
        } else if (block.chainid == 421_614) {
            return ("aavePool", "mockYieldVault");
        } else {
            return ("venueReal", "venueMock");
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
}
