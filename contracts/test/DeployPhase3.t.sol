// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Test } from "forge-std/Test.sol";
import { ERC1967Proxy } from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";

import { ClassIds } from "../src/ClassIds.sol";
import { DeployPhase3 } from "../script/DeployPhase3.s.sol";
import { AllocatorRegistry } from "../src/AllocatorRegistry.sol";
import { IAllocatorRegistry } from "../src/interfaces/IAllocatorRegistry.sol";
import { AllocatorVault } from "../src/AllocatorVault.sol";
import { ReputationAnchor } from "../src/ReputationAnchor.sol";
import { UserVault } from "../src/UserVault.sol";
import { StrategyRegistry } from "../src/StrategyRegistry.sol";
import { MockERC20 } from "./mocks/MockERC20.sol";

/// @notice WS3.B — sanity check that `DeployPhase3.runWith(...)` deploys
///         the Helix `AllocatorVault` proxy, registers it on the existing
///         `AllocatorRegistry` under the shadow name, and merges the new
///         addresses into the deployments JSON without losing Phase-1/2
///         entries. Mirrors `DeployPhase2.t.sol`'s pattern: assertions go
///         through `runWith` instead of `run()` so the tests don't depend
///         on `vm.envOr`, which Foundry's parallel runner cannot serialise
///         between worker threads.
contract DeployPhase3Test is Test {
    DeployPhase3 internal script;

    uint256 internal deployerPk = 0xC0FFEEBEEF;
    address internal deployer;

    MockERC20 internal stake;
    AllocatorRegistry internal allocatorRegistry;
    StrategyRegistry internal strategyRegistry;
    address internal userVault;
    ReputationAnchor internal anchor;
    address internal repSigner = address(0xBEEF1234);

    string internal outFile;
    string internal outLabel;

    uint256 internal constant HELIX_STAKE = 5000e6;
    uint16 internal constant HELIX_FEE_BPS = 600;

    function setUp() public {
        deployer = vm.addr(deployerPk);

        // Phase-1 surface DeployPhase3 hard-depends on.
        stake = new MockERC20("Mock USDC", "mUSDC");
        anchor = new ReputationAnchor(repSigner, address(0), deployer);
        strategyRegistry = new StrategyRegistry(stake, address(anchor), deployer, 7 days);
        allocatorRegistry = new AllocatorRegistry(stake, address(anchor), deployer, 7 days);

        // UserVault behind a proxy — DeployPhase3 only stores the address
        // in the AllocatorVault initializer, no calls into it during
        // registration, so the bare proxy is enough for these tests.
        UserVault uvImpl = new UserVault();
        bytes memory uvInit = abi.encodeCall(UserVault.initialize, (stake, 30 days, deployer));
        userVault = address(new ERC1967Proxy(address(uvImpl), uvInit));

        // Stake budget for the registration.
        stake.mint(deployer, 1_000_000e6);

        script = new DeployPhase3();
    }

    /// @dev Each test seeds its own unique output path + base JSON so
    ///      Foundry's parallel runner never collides on the same file
    ///      between worker threads.
    function _freshOutLabel(string memory suffix) internal returns (string memory) {
        outLabel = string.concat("deploy-phase3-test-", suffix);
        outFile = string.concat("./deployments/", outLabel, ".json");
        vm.writeFile(outFile, _basePhase2Json());
        return outLabel;
    }

    function _basePhase2Json() internal view returns (string memory) {
        // Minimal Phase-2 shape: chainId / deployedAt / phase / a phase-2
        // timestamp the carry-forward must preserve, and the four
        // .addresses keys DeployPhase3 reads.
        return string.concat(
            '{\n  "chainId": 31337,\n  "deployedAt": 1,\n  "phase": "2",\n',
            '  "phase2DeployedAt": 42,\n',
            '  "addresses": {\n',
            '    "usdc": "',
            _toLowerHex(address(stake)),
            '",\n',
            '    "allocatorRegistry": "',
            _toLowerHex(address(allocatorRegistry)),
            '",\n',
            '    "strategyRegistry": "',
            _toLowerHex(address(strategyRegistry)),
            '",\n',
            '    "userVault": "',
            _toLowerHex(userVault),
            '"\n  }\n}\n'
        );
    }

    function _inputs(string memory suffix) internal returns (DeployPhase3.Inputs memory) {
        return DeployPhase3.Inputs({
            deployerPk: deployerPk,
            allocatorRegistry: address(allocatorRegistry),
            userVault: userVault,
            strategyRegistry: address(strategyRegistry),
            stakeToken: stake,
            helixOperator: deployer,
            feeRateBps: HELIX_FEE_BPS,
            stakeAmount: HELIX_STAKE,
            outLabel: _freshOutLabel(suffix)
        });
    }

    // ── Behavioural assertions ─────────────────────────────────────

    function test_DeploysHelixVaultAndRegistersOnRegistry() public {
        DeployPhase3.Phase3Addresses memory a = script.runWith(_inputs("registers"));

        // Vault correctly initialised — Helix gets its own AllocatorVault.
        AllocatorVault helix = AllocatorVault(a.helixAllocatorVault);
        assertEq(address(helix.baseAsset()), address(stake), "vault.baseAsset");
        assertEq(helix.userVault(), userVault, "vault.userVault");
        assertEq(helix.strategyRegistry(), address(strategyRegistry), "vault.strategyRegistry");
        assertEq(helix.operator(), deployer, "vault.operator");
        assertEq(helix.allocatorFeeRateBps(), HELIX_FEE_BPS, "vault.feeRateBps");
        assertEq(helix.owner(), deployer, "vault.owner");

        // Registry entry — name shadowed, fee 600bps, stake locked.
        assertEq(a.helixAllocatorId, a.helixAllocatorVault, "id == vault");
        assertEq(allocatorRegistry.allocatorByName("Helios Helix-shadow"), a.helixAllocatorVault);
        IAllocatorRegistry.AllocatorEntry memory e =
            allocatorRegistry.allocatorOf(a.helixAllocatorVault);
        assertEq(e.name, "Helios Helix-shadow");
        assertEq(e.feeRateBps, HELIX_FEE_BPS);
        assertEq(e.stakeAmount, HELIX_STAKE);
        assertEq(e.supportedClasses.length, 3);
        assertEq(e.supportedClasses[0], ClassIds.MOMENTUM_V1);
        assertEq(e.supportedClasses[1], ClassIds.MEAN_REVERSION_V1);
        assertEq(e.supportedClasses[2], ClassIds.YIELD_ROTATION_V1);
        assertTrue(e.active);
        assertFalse(e.isReferenceBrand, "phase-3 deploy should NOT auto-flip the brand flag");
    }

    /// @dev Phase-1 already pre-seeds "helios helix" as reserved (registry
    ///      constructor). The deploy script registers under the shadow
    ///      name so registration succeeds; this test pins the underlying
    ///      revert behaviour that makes the shadow indirection necessary.
    function test_RegisteringReservedHelixNameReverts() public {
        bytes32[] memory supported = new bytes32[](3);
        supported[0] = ClassIds.MOMENTUM_V1;
        supported[1] = ClassIds.MEAN_REVERSION_V1;
        supported[2] = ClassIds.YIELD_ROTATION_V1;

        vm.startPrank(deployer);
        stake.approve(address(allocatorRegistry), type(uint256).max);
        vm.expectRevert(IAllocatorRegistry.ReservedName.selector);
        allocatorRegistry.registerAllocator(
            "Helios Helix",
            makeAddr("squatter"),
            keccak256("squat"),
            supported,
            HELIX_FEE_BPS,
            HELIX_STAKE
        );
        vm.stopPrank();
    }

    /// @dev Models the post-deploy multi-sig follow-up: owner reserves the
    ///      shadow name held by the registered Helix entry, then assigns
    ///      the reference-brand flag. `assignReferenceBrand` keys off
    ///      `_reservedNames[_nameKey(entry.name)]`, so the shadow name
    ///      must be reserved before the flag flip is allowed.
    function test_AssignReferenceBrand_FollowUpFlow() public {
        DeployPhase3.Phase3Addresses memory a = script.runWith(_inputs("brand-followup"));

        vm.startPrank(deployer);
        allocatorRegistry.reserveName("Helios Helix-shadow");
        allocatorRegistry.assignReferenceBrand(a.helixAllocatorVault);
        vm.stopPrank();

        IAllocatorRegistry.AllocatorEntry memory e =
            allocatorRegistry.allocatorOf(a.helixAllocatorVault);
        assertTrue(e.isReferenceBrand, "brand flag should flip post-reserve+assign");
    }

    function test_AssignReferenceBrand_RevertsIfShadowNameUnreserved() public {
        DeployPhase3.Phase3Addresses memory a = script.runWith(_inputs("brand-norez"));

        vm.prank(deployer);
        vm.expectRevert(AllocatorRegistry.NameNotReserved.selector);
        allocatorRegistry.assignReferenceBrand(a.helixAllocatorVault);
    }

    function test_PatchesDeploymentsJsonInPlace() public {
        DeployPhase3.Phase3Addresses memory a = script.runWith(_inputs("json-merge"));

        string memory raw = vm.readFile(outFile);
        assertEq(vm.parseJsonString(raw, ".phase"), "3", "phase should bump to 3");
        assertGt(vm.parseJsonUint(raw, ".phase3DeployedAt"), 0, "phase3DeployedAt unset");
        assertEq(vm.parseJsonUint(raw, ".phase2DeployedAt"), 42, "phase2DeployedAt lost");

        // New helix slots present.
        assertEq(vm.parseJsonAddress(raw, ".addresses.helixAllocatorVault"), a.helixAllocatorVault);
        assertEq(vm.parseJsonAddress(raw, ".addresses.helixAllocatorId"), a.helixAllocatorId);

        // Phase-1/2 keys carried forward unmodified.
        assertEq(vm.parseJsonAddress(raw, ".addresses.usdc"), address(stake));
        assertEq(
            vm.parseJsonAddress(raw, ".addresses.allocatorRegistry"), address(allocatorRegistry)
        );
        assertEq(vm.parseJsonAddress(raw, ".addresses.strategyRegistry"), address(strategyRegistry));
        assertEq(vm.parseJsonAddress(raw, ".addresses.userVault"), userVault);
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
