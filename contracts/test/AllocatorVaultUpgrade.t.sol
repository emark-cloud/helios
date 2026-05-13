// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Test } from "forge-std/Test.sol";
import { ClassIds } from "../src/ClassIds.sol";
import { AllocatorVault } from "../src/AllocatorVault.sol";
import { IAllocatorVault } from "../src/interfaces/IAllocatorVault.sol";
import { StrategyVault } from "../src/StrategyVault.sol";
import { IStrategyVault } from "../src/interfaces/IStrategyVault.sol";
import { StrategyRegistry } from "../src/StrategyRegistry.sol";
import { TradeAttestationVerifier } from "../src/TradeAttestationVerifier.sol";
import { MockERC20 } from "./mocks/MockERC20.sol";
import { MockGroth16Verifier } from "./mocks/MockGroth16Verifier.sol";
import { MockOracleAnchor } from "./mocks/MockOracleAnchor.sol";
import { MockUserVault } from "./mocks/MockUserVault.sol";
import { MetaStrategyLib } from "../src/interfaces/IMetaStrategy.sol";
import { ERC1967Proxy } from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";
import { Ownable } from "@openzeppelin/contracts/access/Ownable.sol";

/// @notice WS11 — covers the new `setStrategyRegistry` setter on
///         AllocatorVault and asserts UUPS upgrade preserves storage.
contract AllocatorVaultUpgradeTest is Test {
    AllocatorVault internal vault;
    StrategyRegistry internal regV1;
    StrategyRegistry internal regV2; // simulated v3 in the cutover
    StrategyVault internal strat;
    TradeAttestationVerifier internal verifier;
    MockGroth16Verifier internal classVerifier;
    MockERC20 internal usdc;
    MockUserVault internal userVault;
    MockOracleAnchor internal oracleAnchor;

    address internal owner = makeAddr("owner");
    address internal operator = makeAddr("operator");
    address internal stratOp = makeAddr("stratOp");
    address internal navOracle = makeAddr("navOracle");
    address internal user = makeAddr("user");
    address internal rando = makeAddr("rando");

    bytes32 internal constant CLASS_MOM = ClassIds.MOMENTUM_V1;
    uint256 internal constant USER_DEPOSIT = 100_000e6;

    event StrategyRegistryUpdated(address indexed previous, address indexed next);

    function setUp() public {
        usdc = new MockERC20("USDC", "USDC");
        userVault = new MockUserVault(usdc);

        address repAnchor = makeAddr("repAnchor");
        regV1 = new StrategyRegistry(usdc, repAnchor, owner, 7 days);
        regV2 = new StrategyRegistry(usdc, repAnchor, owner, 7 days);

        verifier = new TradeAttestationVerifier(owner);
        classVerifier = new MockGroth16Verifier(true);
        vm.prank(owner);
        verifier.registerVerifier(CLASS_MOM, address(classVerifier));

        AllocatorVault impl = new AllocatorVault();
        bytes memory init = abi.encodeCall(
            AllocatorVault.initialize,
            (usdc, operator, address(userVault), address(regV1), 500, owner)
        );
        vault = AllocatorVault(address(new ERC1967Proxy(address(impl), init)));

        strat = _deployStrategy();

        usdc.mint(stratOp, 5000e6);
        vm.startPrank(stratOp);
        usdc.approve(address(regV1), type(uint256).max);
        regV1.registerStrategy(address(strat), CLASS_MOM, 5000e6);
        vm.stopPrank();

        // Same strategy also registered in regV2 so we can flip and keep
        // allocating; the registry-not-registered test re-creates a fresh
        // regV2 for that one case.
        usdc.mint(stratOp, 5000e6);
        vm.startPrank(stratOp);
        usdc.approve(address(regV2), type(uint256).max);
        regV2.registerStrategy(address(strat), CLASS_MOM, 5000e6);
        vm.stopPrank();

        bytes32[] memory classes = new bytes32[](1);
        classes[0] = CLASS_MOM;
        address[] memory allowedAssets = new address[](1);
        allowedAssets[0] = address(usdc);
        uint32[] memory allowedChains = new uint32[](1);
        allowedChains[0] = uint32(block.chainid);
        userVault.setMeta(
            user,
            MetaStrategyLib.MetaStrategy({
                metaStrategyHash: bytes32(uint256(1)),
                allowedStrategyClasses: classes,
                allowedAssets: allowedAssets,
                allowedChains: allowedChains,
                maxCapital: USER_DEPOSIT,
                maxPerStrategyBps: 10_000,
                maxStrategiesCount: 3,
                drawdownThresholdBps: 1500,
                maxFeeRateBps: 2500,
                rebalanceCadenceSec: 1 days,
                validUntil: uint64(block.timestamp + 30 days),
                defundTwapBars: MetaStrategyLib.DEFAULT_DEFUND_TWAP_BARS,
                defundBondBps: MetaStrategyLib.DEFAULT_DEFUND_BOND_BPS,
                defundConfirmBlocks: MetaStrategyLib.DEFAULT_DEFUND_CONFIRM_BLOCKS
            })
        );
        userVault.setAllocator(user, address(vault));
        usdc.mint(address(this), USER_DEPOSIT);
        usdc.approve(address(userVault), USER_DEPOSIT);
        userVault.deposit(user, USER_DEPOSIT);

        oracleAnchor = new MockOracleAnchor();
        oracleAnchor.setLatest(uint64(block.timestamp));
        vm.prank(owner);
        vault.setOracleAnchor(address(oracleAnchor));
    }

    function _deployStrategy() internal returns (StrategyVault s) {
        address priceAnchor = makeAddr("priceAnchor");
        address yieldAnchor = makeAddr("yieldAnchor");
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
            allocatorVault: address(vault),
            priceAnchor: priceAnchor,
            yieldAnchor: yieldAnchor,
            owner: owner
        });
        s = StrategyVault(
            address(new ERC1967Proxy(address(impl), abi.encodeCall(StrategyVault.initialize, (p))))
        );
    }

    // ── Setter access control ──────────────────────────────────────

    function test_SetStrategyRegistry_OnlyOwner() public {
        vm.prank(rando);
        vm.expectRevert(abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, rando));
        vault.setStrategyRegistry(address(regV2));
    }

    function test_SetStrategyRegistry_RejectsZero() public {
        vm.prank(owner);
        vm.expectRevert(AllocatorVault.ZeroAddress.selector);
        vault.setStrategyRegistry(address(0));
    }

    function test_SetStrategyRegistry_EmitsEvent() public {
        vm.expectEmit(true, true, false, false);
        emit StrategyRegistryUpdated(address(regV1), address(regV2));
        vm.prank(owner);
        vault.setStrategyRegistry(address(regV2));
        assertEq(vault.strategyRegistry(), address(regV2));
    }

    // ── setOperator (signer rotation) ──────────────────────────────

    event OperatorUpdated(address indexed previous, address indexed next);

    function test_SetOperator_OnlyOwner() public {
        vm.prank(rando);
        vm.expectRevert(abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, rando));
        vault.setOperator(address(0xBEEF));
    }

    function test_SetOperator_RejectsZero() public {
        vm.prank(owner);
        vm.expectRevert(AllocatorVault.ZeroAddress.selector);
        vault.setOperator(address(0));
    }

    function test_SetOperator_EmitsEventAndUpdatesStorage() public {
        address newOp = address(0xC0FFEE);
        address prev = vault.operator();
        vm.expectEmit(true, true, false, false);
        emit OperatorUpdated(prev, newOp);
        vm.prank(owner);
        vault.setOperator(newOp);
        assertEq(vault.operator(), newOp);
    }

    // ── Storage preservation through UUPS upgrade ───────────────────

    function test_UUPSUpgrade_PreservesStorageThenSetterSwapsRegistry() public {
        // Allocate against regV1 to populate user state.
        vm.prank(operator);
        vault.allocateToStrategy(user, address(strat), 30_000e6);
        uint256 deployedBefore = vault.userTotalDeployed(user);
        address operatorBefore = vault.operator();
        address userVaultBefore = vault.userVault();
        address registryBefore = vault.strategyRegistry();
        address oracleBefore = vault.oracleAnchor();
        assertEq(deployedBefore, 30_000e6);

        // "Upgrade" to a freshly-deployed impl with the same source.
        // Confirms storage layout still maps cleanly through the proxy.
        AllocatorVault newImpl = new AllocatorVault();
        vm.prank(owner);
        vault.upgradeToAndCall(address(newImpl), "");

        assertEq(vault.userTotalDeployed(user), deployedBefore, "userTotalDeployed drift");
        assertEq(vault.operator(), operatorBefore, "operator drift");
        assertEq(vault.userVault(), userVaultBefore, "userVault drift");
        assertEq(vault.strategyRegistry(), registryBefore, "registry drift");
        assertEq(vault.oracleAnchor(), oracleBefore, "oracleAnchor drift");

        // Swap registry pointer to v2.
        vm.prank(owner);
        vault.setStrategyRegistry(address(regV2));
        assertEq(vault.strategyRegistry(), address(regV2));

        // New allocate routes the registered-check through v2. Strategy is
        // registered in both registries, so the call still succeeds.
        vm.prank(operator);
        vault.allocateToStrategy(user, address(strat), 10_000e6);
        assertEq(vault.userTotalDeployed(user), deployedBefore + 10_000e6);
    }

    function test_SetStrategyRegistry_BlocksAllocateIfUnregisteredInNewRegistry() public {
        // Fresh registry where the strategy was never registered.
        address repAnchor = makeAddr("repAnchor2");
        StrategyRegistry empty = new StrategyRegistry(usdc, repAnchor, owner, 7 days);

        vm.prank(owner);
        vault.setStrategyRegistry(address(empty));

        vm.prank(operator);
        vm.expectRevert(AllocatorVault.StrategyNotRegistered.selector);
        vault.allocateToStrategy(user, address(strat), 30_000e6);
    }
}
