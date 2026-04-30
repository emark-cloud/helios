// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Test } from "forge-std/Test.sol";
import { ERC1967Proxy } from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";

import { RegisterPhase2Strategies } from "../script/RegisterPhase2Strategies.s.sol";
import { StrategyRegistry } from "../src/StrategyRegistry.sol";
import { StrategyVault } from "../src/StrategyVault.sol";
import { IStrategyVault } from "../src/interfaces/IStrategyVault.sol";
import { TradeAttestationVerifier } from "../src/TradeAttestationVerifier.sol";
import { AllocatorVault } from "../src/AllocatorVault.sol";
import { AllocatorRegistry } from "../src/AllocatorRegistry.sol";
import { ReputationAnchor } from "../src/ReputationAnchor.sol";
import { UserVault } from "../src/UserVault.sol";
import { MockSwapRouter } from "../src/mocks/MockSwapRouter.sol";
import { MockERC20 } from "./mocks/MockERC20.sol";
import { MockGroth16Verifier } from "./mocks/MockGroth16Verifier.sol";

/// @notice WS2.B — verify the second-strategy-per-class registration
///         lands cleanly. Runs the full Phase-1 minimal surface, then
///         calls `RegisterPhase2Strategies.runWith(...)` and asserts:
///           - `strategiesByClass(C).length == 2` for each class
///           - both vaults are active
///           - the variant2 vault carries a non-zero, distinct paramsHash
///             (the cohort diversity invariant the §8.2 engine reads)
contract RegisterPhase2StrategiesTest is Test {
    bytes32 internal constant CLASS_MOM = keccak256("momentum_v1");
    bytes32 internal constant CLASS_MR = keccak256("mean_reversion_v1");
    bytes32 internal constant CLASS_YR = keccak256("yield_rotation_v1");

    uint16 internal constant ALLOCATOR_FEE_BPS = 500;
    uint16 internal constant STRATEGY_FEE_BPS_V1 = 1000;
    uint64 internal constant MAX_SESSION_TTL = 30 days;
    uint256 internal constant STAKE_COOLDOWN = 7 days;
    uint256 internal constant STRATEGY_STAKE_V1 = 5000e6;
    uint256 internal constant MAX_CAPACITY = 1_000_000e6;

    RegisterPhase2Strategies internal script;
    address internal deployer;
    uint256 internal deployerPk = 0xA11CEBEEF;

    MockERC20 internal usdc;
    MockSwapRouter internal swapRouter;
    ReputationAnchor internal anchor;
    StrategyRegistry internal strategyRegistry;
    AllocatorRegistry internal allocatorRegistry;
    TradeAttestationVerifier internal tav;
    UserVault internal userVault;
    AllocatorVault internal allocatorVault;
    address internal mockVerifierMom;
    address internal mockVerifierMr;
    address internal mockVerifierYr;

    address internal vaultMomV1;
    address internal vaultMrV1;
    address internal vaultYrV1;

    string internal outLabel;
    string internal outFile;

    function setUp() public {
        deployer = vm.addr(deployerPk);

        usdc = new MockERC20("Mock USDC", "mUSDC");
        usdc.mint(deployer, 10_000_000e6);

        vm.startPrank(deployer);
        swapRouter = new MockSwapRouter(deployer);
        anchor = new ReputationAnchor(deployer, address(0), deployer);
        strategyRegistry = new StrategyRegistry(usdc, address(anchor), deployer, STAKE_COOLDOWN);
        allocatorRegistry = new AllocatorRegistry(usdc, address(anchor), deployer, STAKE_COOLDOWN);
        anchor.setRegistries(address(strategyRegistry), address(allocatorRegistry));

        tav = new TradeAttestationVerifier(deployer);
        mockVerifierMom = address(new MockGroth16Verifier(true));
        mockVerifierMr = address(new MockGroth16Verifier(true));
        mockVerifierYr = address(new MockGroth16Verifier(true));
        tav.registerVerifier(CLASS_MOM, mockVerifierMom);
        tav.registerVerifier(CLASS_MR, mockVerifierMr);
        tav.registerVerifier(CLASS_YR, mockVerifierYr);

        UserVault uvImpl = new UserVault();
        bytes memory uvInit =
            abi.encodeCall(UserVault.initialize, (usdc, MAX_SESSION_TTL, deployer));
        userVault = UserVault(address(new ERC1967Proxy(address(uvImpl), uvInit)));

        AllocatorVault avImpl = new AllocatorVault();
        bytes memory avInit = abi.encodeCall(
            AllocatorVault.initialize,
            (
                usdc,
                deployer,
                address(userVault),
                address(strategyRegistry),
                ALLOCATOR_FEE_BPS,
                deployer
            )
        );
        allocatorVault = AllocatorVault(address(new ERC1967Proxy(address(avImpl), avInit)));

        // Primary strategy vaults (Phase 1 equivalents) — paramsHash = 0
        vaultMomV1 = _deployPrimary(CLASS_MOM);
        vaultMrV1 = _deployPrimary(CLASS_MR);
        vaultYrV1 = _deployPrimary(CLASS_YR);

        usdc.approve(address(strategyRegistry), type(uint256).max);
        strategyRegistry.registerStrategy(vaultMomV1, CLASS_MOM, STRATEGY_STAKE_V1);
        strategyRegistry.registerStrategy(vaultMrV1, CLASS_MR, STRATEGY_STAKE_V1);
        strategyRegistry.registerStrategy(vaultYrV1, CLASS_YR, STRATEGY_STAKE_V1);
        vm.stopPrank();

        script = new RegisterPhase2Strategies();
    }

    function _deployPrimary(bytes32 declaredClass) internal returns (address) {
        StrategyVault impl = new StrategyVault();
        address[] memory universe = new address[](1);
        universe[0] = address(usdc);
        IStrategyVault.StrategyManifest memory m = IStrategyVault.StrategyManifest({
            declaredClass: declaredClass,
            assetUniverse: universe,
            maxCapacity: MAX_CAPACITY,
            feeRateBps: STRATEGY_FEE_BPS_V1,
            operator: deployer,
            stakeAmount: STRATEGY_STAKE_V1,
            paramsHash: bytes32(0)
        });
        bytes memory init = abi.encodeCall(
            StrategyVault.initialize,
            (
                m,
                usdc,
                address(strategyRegistry),
                address(tav),
                address(swapRouter),
                deployer,
                address(allocatorVault),
                deployer
            )
        );
        return address(new ERC1967Proxy(address(impl), init));
    }

    function _freshOutLabel(string memory suffix) internal returns (string memory) {
        outLabel = string.concat("register-phase2-test-", suffix);
        outFile = string.concat("./deployments/", outLabel, ".json");
        vm.writeFile(
            outFile,
            string.concat(
                '{\n  "chainId": 31337,\n  "deployedAt": 1,\n  "phase": "2",\n',
                '  "addresses": {\n',
                '    "strategyVaultMomentum": "',
                _toLowerHex(vaultMomV1),
                '",\n',
                '    "strategyVaultMeanReversion": "',
                _toLowerHex(vaultMrV1),
                '",\n',
                '    "strategyVaultYieldRotation": "',
                _toLowerHex(vaultYrV1),
                '"\n  }\n}\n'
            )
        );
        return outLabel;
    }

    function _inputs(string memory suffix) internal returns (RegisterPhase2Strategies.Inputs memory) {
        return RegisterPhase2Strategies.Inputs({
            deployerPk: deployerPk,
            usdc: address(usdc),
            strategyRegistry: address(strategyRegistry),
            allocatorVault: address(allocatorVault),
            tradeVerifier: address(tav),
            swapRouter: address(swapRouter),
            outLabel: _freshOutLabel(suffix)
        });
    }

    function test_RegistersTwoStrategiesPerClass() public {
        RegisterPhase2Strategies.Variant2Addresses memory v = script.runWith(_inputs("two-per-class"));

        address[] memory mom = strategyRegistry.strategiesByClass(CLASS_MOM);
        address[] memory mr = strategyRegistry.strategiesByClass(CLASS_MR);
        address[] memory yr = strategyRegistry.strategiesByClass(CLASS_YR);
        assertEq(mom.length, 2, "MOM cohort size");
        assertEq(mr.length, 2, "MR cohort size");
        assertEq(yr.length, 2, "YR cohort size");

        assertEq(mom[0], vaultMomV1, "MOM[0] should be primary");
        assertEq(mom[1], v.strategyVaultMomentumVariant2, "MOM[1] should be variant2");
        assertEq(mr[0], vaultMrV1);
        assertEq(mr[1], v.strategyVaultMeanReversionVariant2);
        assertEq(yr[0], vaultYrV1);
        assertEq(yr[1], v.strategyVaultYieldRotationVariant2);
    }

    function test_BothStrategiesActiveAfterRegistration() public {
        RegisterPhase2Strategies.Variant2Addresses memory v = script.runWith(_inputs("active"));

        assertTrue(strategyRegistry.strategyOf(vaultMomV1).active, "MOM v1 active");
        assertTrue(
            strategyRegistry.strategyOf(v.strategyVaultMomentumVariant2).active, "MOM v2 active"
        );
        assertTrue(strategyRegistry.strategyOf(vaultMrV1).active);
        assertTrue(strategyRegistry.strategyOf(v.strategyVaultMeanReversionVariant2).active);
        assertTrue(strategyRegistry.strategyOf(vaultYrV1).active);
        assertTrue(strategyRegistry.strategyOf(v.strategyVaultYieldRotationVariant2).active);
    }

    function test_Variant2HasDistinctParamsHash() public {
        RegisterPhase2Strategies.Variant2Addresses memory v = script.runWith(_inputs("params-hash"));

        bytes32 mom1 = StrategyVault(vaultMomV1).manifest().paramsHash;
        bytes32 mom2 = StrategyVault(v.strategyVaultMomentumVariant2).manifest().paramsHash;
        bytes32 mr1 = StrategyVault(vaultMrV1).manifest().paramsHash;
        bytes32 mr2 = StrategyVault(v.strategyVaultMeanReversionVariant2).manifest().paramsHash;
        bytes32 yr1 = StrategyVault(vaultYrV1).manifest().paramsHash;
        bytes32 yr2 = StrategyVault(v.strategyVaultYieldRotationVariant2).manifest().paramsHash;

        assertEq(mom1, bytes32(0), "primary paramsHash should be zero");
        assertTrue(mom2 != bytes32(0), "variant2 paramsHash should be non-zero");
        assertTrue(mom1 != mom2, "MOM paramsHash should differ");
        assertTrue(mr1 != mr2, "MR paramsHash should differ");
        assertTrue(yr1 != yr2, "YR paramsHash should differ");
        assertTrue(mom2 != mr2, "cross-class paramsHash collision");
        assertTrue(mr2 != yr2, "cross-class paramsHash collision");
        assertTrue(mom2 != yr2, "cross-class paramsHash collision");
    }

    function test_VariantsTakeStakeFromOperator() public {
        uint256 balanceBefore = usdc.balanceOf(deployer);
        script.runWith(_inputs("stake"));
        uint256 balanceAfter = usdc.balanceOf(deployer);
        assertEq(balanceBefore - balanceAfter, 3 * 5000e6, "should pull 3x variant2 stake");
    }

    function test_PatchesDeploymentsJsonInPlace() public {
        RegisterPhase2Strategies.Variant2Addresses memory v = script.runWith(_inputs("json-merge"));

        string memory raw = vm.readFile(outFile);

        assertEq(
            vm.parseJsonAddress(raw, ".addresses.strategyVaultMomentumVariant2"),
            v.strategyVaultMomentumVariant2
        );
        assertEq(
            vm.parseJsonAddress(raw, ".addresses.strategyVaultMeanReversionVariant2"),
            v.strategyVaultMeanReversionVariant2
        );
        assertEq(
            vm.parseJsonAddress(raw, ".addresses.strategyVaultYieldRotationVariant2"),
            v.strategyVaultYieldRotationVariant2
        );

        // Pre-existing primary slots preserved.
        assertEq(vm.parseJsonAddress(raw, ".addresses.strategyVaultMomentum"), vaultMomV1);
        assertEq(vm.parseJsonAddress(raw, ".addresses.strategyVaultMeanReversion"), vaultMrV1);
        assertEq(vm.parseJsonAddress(raw, ".addresses.strategyVaultYieldRotation"), vaultYrV1);

        assertGt(vm.parseJsonUint(raw, ".phase2BVariant2DeployedAt"), 0);
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
