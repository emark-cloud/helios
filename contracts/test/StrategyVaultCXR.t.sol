// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Test } from "forge-std/Test.sol";
import { ClassIds } from "../src/ClassIds.sol";
import { StrategyVault } from "../src/StrategyVault.sol";
import { IStrategyVault } from "../src/interfaces/IStrategyVault.sol";
import { TradeAttestationVerifier } from "../src/TradeAttestationVerifier.sol";
import { MockERC20 } from "./mocks/MockERC20.sol";
import { MockGroth16Verifier } from "./mocks/MockGroth16Verifier.sol";
import { ERC1967Proxy } from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";
import { Ownable } from "@openzeppelin/contracts/access/Ownable.sol";

/// @notice CXR-0b — Exercise the new cross-chain hooks on StrategyVault:
///         setBridgeReceiver, setOftAdapter, onCrossChainAllocate
///         (auth + accounting). The defundCrossChain path involves a
///         real OFT send and is verified end-to-end against forks in
///         the broadcast suite; here we cover the accounting + auth.
contract StrategyVaultCXRTest is Test {
    StrategyVault internal impl;
    StrategyVault internal vault;
    TradeAttestationVerifier internal verifier;
    MockGroth16Verifier internal classVerifier;
    MockERC20 internal usdc;
    MockERC20 internal eth;

    address internal owner = makeAddr("owner");
    address internal operator = makeAddr("operator");
    address internal allocatorVault = makeAddr("allocatorVault");
    address internal registry = makeAddr("registry");
    address internal allowedRouter = makeAddr("router");
    address internal priceAnchor = makeAddr("priceAnchor");
    address internal yieldAnchor = makeAddr("yieldAnchor");
    address internal navOracle = makeAddr("navOracle");
    address internal bridgeReceiver = makeAddr("bridgeReceiver");
    address internal oftAdapter = makeAddr("oftAdapter");
    address internal user = makeAddr("user");

    bytes32 internal constant CLASS = ClassIds.MOMENTUM_V1;

    function setUp() public {
        usdc = new MockERC20("USDC", "USDC");
        eth = new MockERC20("ETH", "ETH");
        verifier = new TradeAttestationVerifier(owner);
        classVerifier = new MockGroth16Verifier(true);
        vm.prank(owner);
        verifier.registerVerifier(CLASS, address(classVerifier));

        address[] memory universe = new address[](2);
        universe[0] = address(usdc);
        universe[1] = address(eth);
        IStrategyVault.StrategyManifest memory m = IStrategyVault.StrategyManifest({
            declaredClass: CLASS,
            assetUniverse: universe,
            maxCapacity: 1_000_000e18,
            feeRateBps: 1000,
            operator: operator,
            stakeAmount: 5000e18,
            paramsHash: bytes32(uint256(0xfee5))
        });

        impl = new StrategyVault(priceAnchor, yieldAnchor);
        StrategyVault.InitParams memory p = StrategyVault.InitParams({
            manifest: m,
            baseAsset: usdc,
            registry: registry,
            verifier: address(verifier),
            allowedRouter: allowedRouter,
            navOracle: navOracle,
            allocatorVault: allocatorVault,
            priceAnchor: priceAnchor,
            yieldAnchor: yieldAnchor,
            owner: owner
        });
        vault = StrategyVault(
            address(new ERC1967Proxy(address(impl), abi.encodeCall(StrategyVault.initialize, (p))))
        );
    }

    function test_setBridgeReceiver_onlyOwner() public {
        vm.prank(makeAddr("rando"));
        vm.expectRevert(
            abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, makeAddr("rando"))
        );
        vault.setBridgeReceiver(bridgeReceiver);
    }

    function test_setBridgeReceiver_storesAddress() public {
        vm.prank(owner);
        vault.setBridgeReceiver(bridgeReceiver);
        assertEq(vault.bridgeReceiver(), bridgeReceiver);
    }

    function test_setOftAdapter_storesAddress() public {
        vm.prank(owner);
        vault.setOftAdapter(oftAdapter);
        assertEq(vault.oftAdapter(), oftAdapter);
    }

    function test_onCrossChainAllocate_rejectsUnauthorized() public {
        vm.expectRevert(StrategyVault.NotBridgeReceiver.selector);
        vault.onCrossChainAllocate(100e6, user);
    }

    function test_onCrossChainAllocate_creditsBookAndNAV() public {
        vm.prank(owner);
        vault.setBridgeReceiver(bridgeReceiver);

        // Simulate the BridgeReceiver having transferred USDC to the
        // vault prior to calling the hook.
        usdc.mint(address(vault), 1000e6);

        vm.prank(bridgeReceiver);
        vault.onCrossChainAllocate(1000e6, user);

        assertEq(vault.allocationOf(allocatorVault), 1000e6);
        assertEq(vault.totalNAV(), 1000e6);
        assertEq(vault.totalCrossChainAllocated(), 1000e6);
    }

    function test_onCrossChainAllocate_rejectsZeroAmount() public {
        vm.prank(owner);
        vault.setBridgeReceiver(bridgeReceiver);
        vm.prank(bridgeReceiver);
        vm.expectRevert(StrategyVault.NonZeroValue.selector);
        vault.onCrossChainAllocate(0, user);
    }

    function test_onCrossChainAllocate_accumulatesAcrossDeposits() public {
        vm.prank(owner);
        vault.setBridgeReceiver(bridgeReceiver);
        usdc.mint(address(vault), 500e6);
        usdc.mint(address(vault), 250e6);

        vm.prank(bridgeReceiver);
        vault.onCrossChainAllocate(500e6, user);
        vm.prank(bridgeReceiver);
        vault.onCrossChainAllocate(250e6, user);

        assertEq(vault.totalCrossChainAllocated(), 750e6);
        assertEq(vault.allocationOf(allocatorVault), 750e6);
    }
}
