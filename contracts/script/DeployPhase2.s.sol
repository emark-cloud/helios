// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";

import { TradeAttestationVerifier } from "../src/TradeAttestationVerifier.sol";
import { StrategyRegistry } from "../src/StrategyRegistry.sol";
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
import { ReputationAnchorV2 } from "../src/ReputationAnchorV2.sol";
import { OraclePriceAnchor } from "../src/OraclePriceAnchor.sol";
import { OracleYieldAnchor } from "../src/OracleYieldAnchor.sol";
import { ClassIds } from "../src/ClassIds.sol";

/// @notice Phase-2 canonical deploy. Reads Phase-1 infrastructure addresses
///         from env, then layers on the Phase-2 surface in a single
///         broadcast:
///
///         1. Real per-class Groth16 verifiers + adapters (replaces the
///            Phase-1 mock-Groth16 placeholders registered at
///            `DeployPhase1.s.sol:104-110`).
///         2. `TradeAttestationVerifier.registerVerifier(class, adapter)`
///            for momentum / mean-reversion / yield-rotation. The class
///            map is mutable per Phase 1, so this swap is a single
///            `onlyOwner` call per class.
///         3. `OraclePriceAnchor` + `OracleYieldAnchor` (EIP-712
///            append-only ledgers; Phase 2 WS1.A wired the oracle service
///            to broadcast once these addresses are known).
///         4. `ReputationAnchorV2` — fresh deploy. V1 was non-upgradeable,
///            so v2 ships as a sibling rather than a UUPS upgrade. The
///            existing registries' `immutable reputationAnchor` keeps V1
///            wired for stake-side delta propagation; V2 is the audit
///            anchor (binds `componentsHash` per §8.2). Phase 5 redeploys
///            the registries pointing at V2.
///         5. `StrategyRegistry.setMarketAllowlistRoot(CLASS_YR, root)` —
///            optional, gated on `YR_MARKET_ALLOWLIST_ROOT` being set.
///         6. Merges all new addresses into `deployments/<chain>.json`
///            (or `OUT_LABEL`) without rewriting the Phase-1 entries.
///
///         Required env:
///           - DEPLOYER_PK
///           - TRADE_VERIFIER  (Phase-1 TradeAttestationVerifier)
///           - STRATEGY_REGISTRY
///           - ALLOCATOR_REGISTRY
///           - REP_SIGNER
///         Optional env:
///           - REP_OAPP                    (default: address(0))
///           - ORACLE_PRICE_SIGNER         (default: deployer)
///           - ORACLE_YIELD_SIGNER         (default: deployer)
///           - YR_MARKET_ALLOWLIST_ROOT    (default: 0x00…00 — left unset)
///           - OUT_LABEL                   (default: chain name; mirrors
///             DeployPhase1's anvil-vs-testnet split)
///
///         Backwards compat: only mutates `TradeAttestationVerifier` and
///         `StrategyRegistry` (per WS3.A both expose owner-gated setters).
///         Vault proxies are not touched. No mainnet impact.
contract DeployPhase2 is Script {
    bytes32 internal constant CLASS_MOM = ClassIds.MOMENTUM_V1;
    bytes32 internal constant CLASS_MR = ClassIds.MEAN_REVERSION_V1;
    bytes32 internal constant CLASS_YR = ClassIds.YIELD_ROTATION_V1;

    struct Phase2Addresses {
        address momentumVerifier;
        address momentumVerifierAdapter;
        address meanReversionVerifier;
        address meanReversionVerifierAdapter;
        address yieldRotationVerifier;
        address yieldRotationVerifierAdapter;
        address reputationAnchorV2;
        address oraclePriceAnchor;
        address oracleYieldAnchor;
    }

    /// @notice Inputs for the parameterized entry point. Production deploys
    ///         use `run()` which reads these from env; tests instantiate
    ///         the struct directly via `runWith` to avoid process-shared
    ///         env-var races between parallel Foundry tests.
    struct Inputs {
        uint256 deployerPk;
        TradeAttestationVerifier tav;
        address strategyRegistry;
        address allocatorRegistry;
        address repSigner;
        address repOApp;
        address priceSigner;
        address yieldSigner;
        bytes32 yrAllowlistRoot;
        string outLabel;
    }

    function run() external returns (Phase2Addresses memory a) {
        uint256 pk = vm.envUint("DEPLOYER_PK");
        address deployer = vm.addr(pk);

        Inputs memory i = Inputs({
            deployerPk: pk,
            tav: TradeAttestationVerifier(vm.envAddress("TRADE_VERIFIER")),
            strategyRegistry: vm.envAddress("STRATEGY_REGISTRY"),
            allocatorRegistry: vm.envAddress("ALLOCATOR_REGISTRY"),
            repSigner: vm.envAddress("REP_SIGNER"),
            repOApp: vm.envOr("REP_OAPP", address(0)),
            priceSigner: vm.envOr("ORACLE_PRICE_SIGNER", deployer),
            yieldSigner: vm.envOr("ORACLE_YIELD_SIGNER", deployer),
            yrAllowlistRoot: vm.envOr("YR_MARKET_ALLOWLIST_ROOT", bytes32(0)),
            outLabel: vm.envOr("OUT_LABEL", _chainName())
        });
        return runWith(i);
    }

    function runWith(Inputs memory i) public returns (Phase2Addresses memory a) {
        address deployer = vm.addr(i.deployerPk);

        vm.startBroadcast(i.deployerPk);
        _deployVerifiers(a);
        _rotateClassMap(i.tav, a);
        _deployAnchors(a, deployer, i.repSigner, i.repOApp, i.priceSigner, i.yieldSigner);
        ReputationAnchorV2(a.reputationAnchorV2)
            .setRegistries(i.strategyRegistry, i.allocatorRegistry);
        if (i.yrAllowlistRoot != bytes32(0)) {
            StrategyRegistry(i.strategyRegistry).setMarketAllowlistRoot(CLASS_YR, i.yrAllowlistRoot);
        }
        vm.stopBroadcast();

        _logAndPersist(a, i.yrAllowlistRoot, i.outLabel);
    }

    function _deployVerifiers(Phase2Addresses memory a) internal {
        MomentumV1Verifier momRaw = new MomentumV1Verifier();
        a.momentumVerifier = address(momRaw);
        a.momentumVerifierAdapter = address(new MomentumV1VerifierAdapter(address(momRaw)));

        MeanReversionV1Verifier mrRaw = new MeanReversionV1Verifier();
        a.meanReversionVerifier = address(mrRaw);
        a.meanReversionVerifierAdapter = address(new MeanReversionV1VerifierAdapter(address(mrRaw)));

        YieldRotationV1Verifier yrRaw = new YieldRotationV1Verifier();
        a.yieldRotationVerifier = address(yrRaw);
        a.yieldRotationVerifierAdapter = address(new YieldRotationV1VerifierAdapter(address(yrRaw)));
    }

    /// @dev TAV's `registerVerifier` is now first-set-only (Phase-3 review
    ///      MEDIUM). For each class, register if unset, otherwise queue a
    ///      timelocked replacement via `proposeVerifierChange`. The caller
    ///      is responsible for `commitVerifierChange` after `CHANGE_DELAY`.
    ///      Phase 6 mainnet deploys a fresh TAV, so it always takes the
    ///      `registerVerifier` branch in production.
    function _rotateClassMap(TradeAttestationVerifier tav, Phase2Addresses memory a) internal {
        _registerOrPropose(tav, CLASS_MOM, a.momentumVerifierAdapter);
        _registerOrPropose(tav, CLASS_MR, a.meanReversionVerifierAdapter);
        _registerOrPropose(tav, CLASS_YR, a.yieldRotationVerifierAdapter);
    }

    function _registerOrPropose(TradeAttestationVerifier tav, bytes32 class, address newVerifier)
        internal
    {
        if (tav.verifierOf(class) == address(0)) {
            tav.registerVerifier(class, newVerifier);
        } else {
            tav.proposeVerifierChange(class, newVerifier);
        }
    }

    function _deployAnchors(
        Phase2Addresses memory a,
        address deployer,
        address repSigner,
        address repOApp,
        address priceSigner,
        address yieldSigner
    ) internal {
        a.reputationAnchorV2 = address(new ReputationAnchorV2(repSigner, repOApp, deployer));
        a.oraclePriceAnchor = address(new OraclePriceAnchor(priceSigner, deployer));
        a.oracleYieldAnchor = address(new OracleYieldAnchor(yieldSigner, deployer));
    }

    // ── Logging + JSON persistence ─────────────────────────────────

    function _logAndPersist(Phase2Addresses memory a, bytes32 yrRoot, string memory label)
        internal
    {
        _logAddresses(a, yrRoot);
        string memory file = string.concat("./deployments/", label, ".json");
        _patchJson(file, a);
        console2.log("merged into:", file);
    }

    /// @dev Merges Phase-2 addresses into `deployments/<chain>.json`. The
    ///      existing file (Phase-1 deploy artifact) is read, every key
    ///      under `.addresses` is copied forward, then the Phase-2 keys
    ///      are layered on top (overriding the mock-verifier slots that
    ///      Phase-1 wrote with the new raw-verifier addresses, and adding
    ///      the adapters / V2 anchor / oracle anchors as fresh keys).
    ///      Top-level: `phase` bumps to "2", `phase2DeployedAt` is
    ///      stamped, `chainId` and `deployedAt` carry over from Phase 1.
    ///
    ///      We rebuild + rewrite the whole file because Foundry's
    ///      `vm.writeJson(json, path, valueKey)` cannot create new
    ///      nested keys — it only replaces existing ones — and the
    ///      `vm.serialize*` family flattens nested objects to escaped
    ///      strings rather than embedded JSON, which is wrong for our
    ///      schema. String concat with the existing keys preserved
    ///      keeps the output diffable + matches the Phase-1 pretty-print
    ///      style.
    function _patchJson(string memory file, Phase2Addresses memory a) internal {
        string memory raw = vm.readFile(file);
        uint256 chainIdVal = vm.parseJsonUint(raw, ".chainId");
        uint256 deployedAtVal = vm.parseJsonUint(raw, ".deployedAt");

        string memory addrsBody = _phase1Addresses(raw);
        addrsBody = string.concat(addrsBody, _phase2Addresses(a));

        string memory merged = string.concat(
            "{\n",
            '  "chainId": ',
            vm.toString(chainIdVal),
            ",\n",
            '  "deployedAt": ',
            vm.toString(deployedAtVal),
            ',\n  "phase": "2",\n',
            '  "phase2DeployedAt": ',
            vm.toString(block.timestamp),
            ',\n  "addresses": {\n',
            addrsBody,
            "  }\n}\n"
        );
        vm.writeFile(file, merged);
    }

    /// @dev Carry-forward block: every existing `.addresses.*` key whose
    ///      slot Phase-2 will *not* overwrite. The skipped keys are the
    ///      Phase-1 mock-verifier slots — Phase 2 re-emits them with the
    ///      real verifier addresses in `_phase2Addresses`.
    function _phase1Addresses(string memory raw) internal pure returns (string memory body) {
        string[] memory keys = vm.parseJsonKeys(raw, ".addresses");
        for (uint256 i = 0; i < keys.length; i++) {
            string memory k = keys[i];
            if (_isPhase2OverrideKey(k)) continue;
            address v = vm.parseJsonAddress(raw, string.concat(".addresses.", k));
            body = string.concat(body, _kv(k, v));
        }
    }

    function _phase2Addresses(Phase2Addresses memory a) internal pure returns (string memory) {
        return string.concat(
            _kv("momentumVerifier", a.momentumVerifier),
            _kv("meanReversionVerifier", a.meanReversionVerifier),
            _kv("yieldRotationVerifier", a.yieldRotationVerifier),
            _kv("momentumVerifierAdapter", a.momentumVerifierAdapter),
            _kv("meanReversionVerifierAdapter", a.meanReversionVerifierAdapter),
            _kv("yieldRotationVerifierAdapter", a.yieldRotationVerifierAdapter),
            _kv("reputationAnchorV2", a.reputationAnchorV2),
            _kv("oraclePriceAnchor", a.oraclePriceAnchor),
            _kvLast("oracleYieldAnchor", a.oracleYieldAnchor)
        );
    }

    function _isPhase2OverrideKey(string memory k) internal pure returns (bool) {
        bytes32 h = keccak256(bytes(k));
        return h == keccak256("momentumVerifier") || h == keccak256("meanReversionVerifier")
            || h == keccak256("yieldRotationVerifier");
    }

    function _kv(string memory k, address v) internal pure returns (string memory) {
        return string.concat('    "', k, '": "', _addrLower(v), '",\n');
    }

    function _kvLast(string memory k, address v) internal pure returns (string memory) {
        return string.concat('    "', k, '": "', _addrLower(v), '"\n');
    }

    function _logAddresses(Phase2Addresses memory a, bytes32 yrRoot) internal view {
        console2.log("=== Helios Phase-2 deploy ===");
        console2.log("chainId:                        ", block.chainid);
        console2.log("MomentumV1Verifier:             ", a.momentumVerifier);
        console2.log("MomentumV1VerifierAdapter:      ", a.momentumVerifierAdapter);
        console2.log("MeanReversionV1Verifier:        ", a.meanReversionVerifier);
        console2.log("MeanReversionV1VerifierAdapter: ", a.meanReversionVerifierAdapter);
        console2.log("YieldRotationV1Verifier:        ", a.yieldRotationVerifier);
        console2.log("YieldRotationV1VerifierAdapter: ", a.yieldRotationVerifierAdapter);
        console2.log("ReputationAnchorV2:             ", a.reputationAnchorV2);
        console2.log("OraclePriceAnchor:              ", a.oraclePriceAnchor);
        console2.log("OracleYieldAnchor:              ", a.oracleYieldAnchor);
        if (yrRoot != bytes32(0)) {
            console2.log("YR market allowlist root set:    ");
            console2.logBytes32(yrRoot);
        } else {
            console2.log("YR market allowlist root:       <unset>");
        }
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
