// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Test } from "forge-std/Test.sol";
import { ClassIds } from "../src/ClassIds.sol";

import { DeployPhase2 } from "../script/DeployPhase2.s.sol";
import { TradeAttestationVerifier } from "../src/TradeAttestationVerifier.sol";
import { StrategyRegistry } from "../src/StrategyRegistry.sol";
import { AllocatorRegistry } from "../src/AllocatorRegistry.sol";
import { ReputationAnchor } from "../src/ReputationAnchor.sol";
import { ReputationAnchorV2 } from "../src/ReputationAnchorV2.sol";
import { OraclePriceAnchor } from "../src/OraclePriceAnchor.sol";
import { OracleYieldAnchor } from "../src/OracleYieldAnchor.sol";
import { MockERC20 } from "./mocks/MockERC20.sol";
import { MockGroth16Verifier } from "./mocks/MockGroth16Verifier.sol";

/// @notice WS3.B — sanity check that `DeployPhase2.runWith(...)` rotates
///         the class map, deploys the new anchors, sets the YR allowlist
///         root, and merges every new address into the deployments JSON
///         without losing the Phase-1 entries.
///
///         All assertions go through `runWith` instead of `run()` so the
///         tests don't depend on `vm.envOr`, which Foundry's parallel
///         test runner cannot serialize between worker threads.
contract DeployPhase2Test is Test {
    bytes32 internal constant CLASS_MOM = ClassIds.MOMENTUM_V1;
    bytes32 internal constant CLASS_MR = ClassIds.MEAN_REVERSION_V1;
    bytes32 internal constant CLASS_YR = ClassIds.YIELD_ROTATION_V1;

    bytes32 internal constant YR_ROOT = bytes32(uint256(0xA11CE));

    DeployPhase2 internal script;
    address internal deployer;
    uint256 internal deployerPk = 0xA11CEBEEF;

    TradeAttestationVerifier internal tav;
    StrategyRegistry internal strategyRegistry;
    AllocatorRegistry internal allocatorRegistry;
    ReputationAnchor internal anchorV1;
    address internal repSigner = address(0xBEEFCA5E);

    string internal outFile;
    string internal outLabel;

    address internal momMock;
    address internal mrMock;
    address internal yrMock;

    function setUp() public {
        deployer = vm.addr(deployerPk);

        // ── Phase-1 surface that DeployPhase2 hard-depends on ─────
        MockERC20 stake = new MockERC20("Mock USDC", "mUSDC");
        anchorV1 = new ReputationAnchor(repSigner, address(0), deployer);
        strategyRegistry = new StrategyRegistry(stake, address(anchorV1), deployer, 7 days);
        allocatorRegistry = new AllocatorRegistry(stake, address(anchorV1), deployer, 7 days);
        tav = new TradeAttestationVerifier(deployer);

        momMock = address(new MockGroth16Verifier(true));
        mrMock = address(new MockGroth16Verifier(true));
        yrMock = address(new MockGroth16Verifier(true));
        vm.startPrank(deployer);
        tav.registerVerifier(CLASS_MOM, momMock);
        tav.registerVerifier(CLASS_MR, mrMock);
        tav.registerVerifier(CLASS_YR, yrMock);
        vm.stopPrank();

        script = new DeployPhase2();
    }

    /// @dev Each test seeds its own unique output path + base JSON. The
    ///      caller passes a per-test label suffix because `vm.randomUint`,
    ///      `block.timestamp`, and CREATE-address salts are all
    ///      deterministic across the post-setUp EVM snapshot that
    ///      Foundry restores before every test, so they collide when
    ///      tests run on parallel workers (each worker re-executes from
    ///      the same snapshot). Hardcoded per-test suffixes are the
    ///      only fully race-free option.
    function _freshOutLabel(string memory suffix) internal returns (string memory) {
        outLabel = string.concat("deploy-phase2-test-", suffix);
        outFile = string.concat("./deployments/", outLabel, ".json");
        vm.writeFile(
            outFile,
            string.concat(
                '{\n  "chainId": 31337,\n  "deployedAt": 1,\n  "phase": "1",\n',
                '  "addresses": {\n',
                '    "momentumVerifier": "',
                _toLowerHex(momMock),
                '",\n',
                '    "meanReversionVerifier": "',
                _toLowerHex(mrMock),
                '",\n',
                '    "yieldRotationVerifier": "',
                _toLowerHex(yrMock),
                '"\n  }\n}\n'
            )
        );
        return outLabel;
    }

    function _inputs(string memory suffix, bytes32 yrRoot, address priceSigner, address yieldSigner)
        internal
        returns (DeployPhase2.Inputs memory)
    {
        return DeployPhase2.Inputs({
            deployerPk: deployerPk,
            tav: tav,
            strategyRegistry: address(strategyRegistry),
            allocatorRegistry: address(allocatorRegistry),
            repSigner: repSigner,
            repOApp: address(0),
            priceSigner: priceSigner,
            yieldSigner: yieldSigner,
            yrAllowlistRoot: yrRoot,
            outLabel: _freshOutLabel(suffix)
        });
    }

    function test_RotatesClassMapToRealAdapters() public {
        DeployPhase2.Phase2Addresses memory a =
            script.runWith(_inputs("rotation", YR_ROOT, deployer, deployer));

        // TAV's `registerVerifier` is now first-set-only; replacements
        // queue through `proposeVerifierChange` and require a second tx
        // after `CHANGE_DELAY` (Phase-3 review MEDIUM). The Phase-1 mocks
        // are pre-seeded in `setUp`, so the script proposes; commit here.
        _commitClassMap(a);

        assertEq(tav.verifierOf(CLASS_MOM), a.momentumVerifierAdapter, "MOM not rotated");
        assertEq(tav.verifierOf(CLASS_MR), a.meanReversionVerifierAdapter, "MR not rotated");
        assertEq(tav.verifierOf(CLASS_YR), a.yieldRotationVerifierAdapter, "YR not rotated");
    }

    function _commitClassMap(DeployPhase2.Phase2Addresses memory a) internal {
        // Sanity: verify the script queued the changes.
        (address pendMom,) = tav.pendingChanges(CLASS_MOM);
        assertEq(pendMom, a.momentumVerifierAdapter, "MOM not proposed");

        vm.warp(block.timestamp + tav.CHANGE_DELAY());
        vm.startPrank(deployer);
        tav.commitVerifierChange(CLASS_MOM);
        tav.commitVerifierChange(CLASS_MR);
        tav.commitVerifierChange(CLASS_YR);
        vm.stopPrank();
    }

    function test_DeploysAnchorsAndWiresRegistries() public {
        DeployPhase2.Phase2Addresses memory a =
            script.runWith(_inputs("anchors", YR_ROOT, deployer, deployer));

        ReputationAnchorV2 v2 = ReputationAnchorV2(a.reputationAnchorV2);
        assertEq(address(v2.strategyRegistry()), address(strategyRegistry), "v2.strategyRegistry");
        assertEq(
            address(v2.allocatorRegistry()), address(allocatorRegistry), "v2.allocatorRegistry"
        );
        assertEq(v2.reputationSigner(), repSigner, "v2.signer");
        assertEq(OraclePriceAnchor(a.oraclePriceAnchor).oracleSigner(), deployer, "price.signer");
        assertEq(OracleYieldAnchor(a.oracleYieldAnchor).oracleSigner(), deployer, "yield.signer");
    }

    function test_SetsYieldRotationAllowlistRoot() public {
        script.runWith(_inputs("yr-root-set", YR_ROOT, deployer, deployer));
        assertEq(strategyRegistry.marketAllowlistRoot(CLASS_YR), YR_ROOT, "YR root unset");
    }

    function test_AllowlistRootSkippedWhenZero() public {
        script.runWith(_inputs("yr-root-zero", bytes32(0), deployer, deployer));
        assertEq(strategyRegistry.marketAllowlistRoot(CLASS_YR), bytes32(0), "should stay unset");
    }

    function test_SeparateOraclePriceAndYieldSigners() public {
        address priceSigner = address(0xCAFE0001);
        address yieldSigner = address(0xCAFE0002);
        DeployPhase2.Phase2Addresses memory a =
            script.runWith(_inputs("oracle-signers", YR_ROOT, priceSigner, yieldSigner));

        assertEq(OraclePriceAnchor(a.oraclePriceAnchor).oracleSigner(), priceSigner);
        assertEq(OracleYieldAnchor(a.oracleYieldAnchor).oracleSigner(), yieldSigner);
    }

    function test_PatchesDeploymentsJsonInPlace() public {
        DeployPhase2.Phase2Addresses memory a =
            script.runWith(_inputs("json-merge", YR_ROOT, deployer, deployer));

        string memory raw = vm.readFile(outFile);
        assertEq(vm.parseJsonString(raw, ".phase"), "2", "phase should bump to 2");
        assertGt(vm.parseJsonUint(raw, ".phase2DeployedAt"), 0, "phase2DeployedAt unset");

        // New addresses present.
        assertEq(
            vm.parseJsonAddress(raw, ".addresses.momentumVerifierAdapter"),
            a.momentumVerifierAdapter
        );
        assertEq(
            vm.parseJsonAddress(raw, ".addresses.meanReversionVerifierAdapter"),
            a.meanReversionVerifierAdapter
        );
        assertEq(
            vm.parseJsonAddress(raw, ".addresses.yieldRotationVerifierAdapter"),
            a.yieldRotationVerifierAdapter
        );
        assertEq(vm.parseJsonAddress(raw, ".addresses.reputationAnchorV2"), a.reputationAnchorV2);
        assertEq(vm.parseJsonAddress(raw, ".addresses.oraclePriceAnchor"), a.oraclePriceAnchor);
        assertEq(vm.parseJsonAddress(raw, ".addresses.oracleYieldAnchor"), a.oracleYieldAnchor);

        // Phase-1 mock verifier slots re-pointed at the real raw verifiers.
        assertEq(vm.parseJsonAddress(raw, ".addresses.momentumVerifier"), a.momentumVerifier);
        assertEq(
            vm.parseJsonAddress(raw, ".addresses.meanReversionVerifier"), a.meanReversionVerifier
        );
        assertEq(
            vm.parseJsonAddress(raw, ".addresses.yieldRotationVerifier"), a.yieldRotationVerifier
        );
    }

    function _toLowerHex(address v) internal pure returns (string memory) {
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
