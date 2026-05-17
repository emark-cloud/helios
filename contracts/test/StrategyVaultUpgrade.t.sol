// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Test } from "forge-std/Test.sol";
import { ClassIds } from "../src/ClassIds.sol";
import { StrategyVault } from "../src/StrategyVault.sol";
import { IStrategyVault } from "../src/interfaces/IStrategyVault.sol";
import { StrategyRegistry } from "../src/StrategyRegistry.sol";
import { TradeAttestationVerifier } from "../src/TradeAttestationVerifier.sol";
import { MockERC20 } from "./mocks/MockERC20.sol";
import { MockGroth16Verifier } from "./mocks/MockGroth16Verifier.sol";
import { ERC1967Proxy } from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";
import { Ownable } from "@openzeppelin/contracts/access/Ownable.sol";

/// @notice WS11 — covers the new `setRegistry` setter on StrategyVault
///         and asserts UUPS upgrade preserves storage + paramsHashOf
///         routes through the new registry after the swap.
contract StrategyVaultUpgradeTest is Test {
    StrategyVault internal vault;
    StrategyRegistry internal regV1;
    StrategyRegistry internal regV2;
    TradeAttestationVerifier internal verifier;
    MockGroth16Verifier internal classVerifier;
    MockERC20 internal usdc;

    address internal owner = makeAddr("owner");
    address internal stratOp = makeAddr("stratOp");
    address internal navOracle = makeAddr("navOracle");
    address internal allocVault = makeAddr("allocVault");
    address internal rando = makeAddr("rando");
    address internal priceAnchor = makeAddr("priceAnchor");
    address internal yieldAnchor = makeAddr("yieldAnchor");

    bytes32 internal constant CLASS_MOM = ClassIds.MOMENTUM_V1;
    bytes32 internal constant PARAMS_V1 = keccak256("paramsV1");
    bytes32 internal constant PARAMS_V2 = keccak256("paramsV2");

    event RegistryUpdated(address indexed previous, address indexed next);

    function setUp() public {
        usdc = new MockERC20("USDC", "USDC");
        address repAnchor = makeAddr("repAnchor");

        regV1 = new StrategyRegistry(usdc, repAnchor, owner, 7 days);
        regV2 = new StrategyRegistry(usdc, repAnchor, owner, 7 days);

        verifier = new TradeAttestationVerifier(owner);
        classVerifier = new MockGroth16Verifier(true);
        vm.prank(owner);
        verifier.registerVerifier(CLASS_MOM, address(classVerifier));

        StrategyVault impl = new StrategyVault(priceAnchor, yieldAnchor);
        address[] memory universe = new address[](1);
        universe[0] = address(usdc);
        IStrategyVault.StrategyManifest memory m = IStrategyVault.StrategyManifest({
            declaredClass: CLASS_MOM,
            assetUniverse: universe,
            maxCapacity: 1_000_000e6,
            feeRateBps: 1000,
            operator: stratOp,
            stakeAmount: 5000e6,
            paramsHash: bytes32(0)
        });
        StrategyVault.InitParams memory p = StrategyVault.InitParams({
            manifest: m,
            baseAsset: usdc,
            registry: address(regV1),
            verifier: address(verifier),
            allowedRouter: makeAddr("router"),
            navOracle: navOracle,
            allocatorVault: allocVault,
            priceAnchor: priceAnchor,
            yieldAnchor: yieldAnchor,
            owner: owner
        });
        vault = StrategyVault(
            address(new ERC1967Proxy(address(impl), abi.encodeCall(StrategyVault.initialize, (p))))
        );

        // Register strategy + commit paramsHash on regV1 (the active one).
        usdc.mint(stratOp, 5000e6);
        vm.startPrank(stratOp);
        usdc.approve(address(regV1), type(uint256).max);
        regV1.registerStrategy(address(vault), CLASS_MOM, 5000e6);
        regV1.commitInitialParamsHash(address(vault), PARAMS_V1);
        vm.stopPrank();
    }

    // ── Setter access control ──────────────────────────────────────

    function test_SetRegistry_OnlyOwner() public {
        vm.prank(rando);
        vm.expectRevert(abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, rando));
        vault.setRegistry(address(regV2));
    }

    function test_SetRegistry_RejectsZero() public {
        vm.prank(owner);
        vm.expectRevert(StrategyVault.ZeroAddress.selector);
        vault.setRegistry(address(0));
    }

    function test_SetRegistry_EmitsAndUpdates() public {
        vm.expectEmit(true, true, false, false);
        emit RegistryUpdated(address(regV1), address(regV2));
        vm.prank(owner);
        vault.setRegistry(address(regV2));
        assertEq(vault.registry(), address(regV2));
    }

    // ── setOperator + setNavOracle (signer rotation) ───────────────

    event OperatorUpdated(address indexed previous, address indexed next);
    event NavOracleUpdated(address indexed previous, address indexed next);

    function test_SetOperator_OnlyOwner() public {
        vm.prank(rando);
        vm.expectRevert(abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, rando));
        vault.setOperator(address(0xBEEF));
    }

    function test_SetOperator_RejectsZero() public {
        vm.prank(owner);
        vm.expectRevert(StrategyVault.ZeroAddress.selector);
        vault.setOperator(address(0));
    }

    function test_SetOperator_EmitsAndMutatesManifest() public {
        address newOp = address(0xC0FFEE);
        address prev = vault.manifest().operator;
        vm.expectEmit(true, true, false, false);
        emit OperatorUpdated(prev, newOp);
        vm.prank(owner);
        vault.setOperator(newOp);
        assertEq(vault.manifest().operator, newOp);
    }

    function test_SetNavOracle_OnlyOwner() public {
        vm.prank(rando);
        vm.expectRevert(abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, rando));
        vault.setNavOracle(address(0xBEEF));
    }

    function test_SetNavOracle_RejectsZero() public {
        vm.prank(owner);
        vm.expectRevert(StrategyVault.ZeroAddress.selector);
        vault.setNavOracle(address(0));
    }

    function test_SetNavOracle_EmitsAndUpdates() public {
        address newNav = address(0xDECAF);
        address prev = vault.navOracle();
        vm.expectEmit(true, true, false, false);
        emit NavOracleUpdated(prev, newNav);
        vm.prank(owner);
        vault.setNavOracle(newNav);
        assertEq(vault.navOracle(), newNav);
    }

    // ── Storage preservation + paramsHashOf swap ───────────────────

    function test_UUPSUpgrade_PreservesStorageThenSetterSwapsRegistry() public {
        // Pre-upgrade state.
        address registryBefore = vault.registry();
        address verifierBefore = vault.verifier();
        address allocBefore = vault.allocatorVault();
        address baseAssetBefore = address(vault.baseAsset());
        bool haltedBefore = vault.halted();

        // Read paramsHash through regV1 (sanity).
        assertEq(regV1.paramsHashOf(address(vault)), PARAMS_V1);

        // Re-deploy impl with the same source — proves storage layout maps
        // through the proxy after upgrade.
        StrategyVault newImpl = new StrategyVault(priceAnchor, yieldAnchor);
        vm.prank(owner);
        vault.upgradeToAndCall(address(newImpl), "");

        assertEq(vault.registry(), registryBefore, "registry drift");
        assertEq(vault.verifier(), verifierBefore, "verifier drift");
        assertEq(vault.allocatorVault(), allocBefore, "allocatorVault drift");
        assertEq(address(vault.baseAsset()), baseAssetBefore, "baseAsset drift");
        assertEq(vault.halted(), haltedBefore, "halted drift");

        // Re-register strategy + commit a fresh paramsHash on regV2.
        usdc.mint(stratOp, 5000e6);
        vm.startPrank(stratOp);
        usdc.approve(address(regV2), type(uint256).max);
        regV2.registerStrategy(address(vault), CLASS_MOM, 5000e6);
        regV2.commitInitialParamsHash(address(vault), PARAMS_V2);
        vm.stopPrank();

        // Swap registry pointer.
        vm.prank(owner);
        vault.setRegistry(address(regV2));
        assertEq(vault.registry(), address(regV2));

        // The vault now reads paramsHash through regV2.
        assertEq(
            StrategyRegistry(vault.registry()).paramsHashOf(address(vault)),
            PARAMS_V2,
            "paramsHashOf routes via swapped registry"
        );
    }

    function test_SetRegistry_TrustRebindsForSlash() public {
        // Pre-swap: V1 can slash, V2 cannot.
        vm.prank(address(regV2));
        vm.expectRevert(IStrategyVault.NotRegistry.selector);
        vault.slash("nope");

        // Swap registry pointer to V2.
        vm.prank(owner);
        vault.setRegistry(address(regV2));

        // Post-swap: V1 is no longer trusted, V2 is.
        vm.prank(address(regV1));
        vm.expectRevert(IStrategyVault.NotRegistry.selector);
        vault.slash("nope from old reg");

        vm.prank(address(regV2));
        vault.slash("legit halt from new reg");
        assertTrue(vault.halted());
    }

    /// @notice The defund-unwind UUPS upgrade is function-only (zero
    ///         storage delta): re-deploying the impl preserves all
    ///         state AND `unwindToBase` becomes callable by the
    ///         allocator. The proxy's universe is `[usdc]` so the new
    ///         function is a safe no-op here (proves availability +
    ///         the AllocatorVault-only gate post-upgrade).
    function test_UUPSUpgrade_AddsUnwindToBase_PreservesStorage() public {
        address allocBefore = vault.allocatorVault();
        address baseBefore = address(vault.baseAsset());

        StrategyVault newImpl = new StrategyVault(priceAnchor, yieldAnchor);
        vm.prank(owner);
        vault.upgradeToAndCall(address(newImpl), "");

        assertEq(vault.allocatorVault(), allocBefore, "allocatorVault drift");
        assertEq(address(vault.baseAsset()), baseBefore, "baseAsset drift");

        // Gate holds post-upgrade.
        vm.prank(rando);
        vm.expectRevert(StrategyVault.NotAllocatorVault.selector);
        vault.unwindToBase();

        // Allocator can call it; `[usdc]`-only universe → no-op.
        vm.prank(allocVault);
        vault.unwindToBase();
    }
}
