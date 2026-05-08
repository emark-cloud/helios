// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Test, console2 } from "forge-std/Test.sol";

import { UserVault } from "../src/UserVault.sol";
import { AllocatorVault } from "../src/AllocatorVault.sol";
import { StrategyVault } from "../src/StrategyVault.sol";
import { StrategyRegistry } from "../src/StrategyRegistry.sol";
import { IStrategyRegistry } from "../src/interfaces/IStrategyRegistry.sol";

import { RedeployBaseTrioStrategyVaults } from "../script/RedeployBaseTrioStrategyVaults.s.sol";

interface IUUPS {
    function upgradeToAndCall(address newImpl, bytes memory data) external;
}

interface IOwnable {
    function owner() external view returns (address);
}

/// @notice Fork test for the Phase-3 follow-up upgrades against the live
///         Kite testnet state. Verifies, against actual on-chain proxies,
///         that:
///           1. Pre-upgrade, the gap is real (paused() reverts on
///              UserVault + AllocatorVault; userTotalDeployed reverts).
///           2. UpgradeUserAndAllocatorVaults — fresh impls deploy and
///              upgradeToAndCall lands; pause/unpause/userTotalDeployed
///              all work post-upgrade.
///           3. RedeployBaseTrioStrategyVaults — three fresh proxies
///              deploy on the Phase-3 impl, register cleanly, expose
///              paused(), carry the new paramsHash, and the JSON merge
///              overwrites the base-trio keys without touching the
///              variant2/variant3 entries. Legacy registrations stay
///              registered (intentional; deactivation is an operator
///              decision).
///
///         Skipped silently when KITE_RPC_URL is unset so CI without the
///         RPC passes. Run locally with:
///           KITE_RPC_URL=$KITE_RPC_URL forge test \
///             --match-contract Phase3FollowupForkTest -vv
contract Phase3FollowupForkTest is Test {
    /// EIP-1967 implementation slot.
    bytes32 internal constant EIP1967_IMPL_SLOT =
        0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc;

    uint256 internal constant KITE_TESTNET_CHAIN_ID = 2368;
    string internal constant DEPLOYMENTS_FILE = "./deployments/kite-testnet.json";
    string internal constant TEST_LABEL = "phase3-followup-fork-test";
    string internal constant TEST_FILE = "./deployments/phase3-followup-fork-test.json";

    address internal usdc;
    address internal swapRouter;
    address internal strategyRegistry;
    address internal allocatorVault;
    address internal userVault;
    address internal tav;
    address internal priceAnchor;
    address internal yieldAnchor;
    address internal legacyMomentum;
    address internal legacyMeanReversion;
    address internal legacyYieldRotation;

    address internal vaultsOwner;

    function setUp() public {
        string memory rpc = vm.envOr("KITE_RPC_URL", string(""));
        if (bytes(rpc).length == 0) {
            console2.log("KITE_RPC_URL unset - skipping Phase-3 follow-up fork test");
            vm.skip(true);
            return;
        }
        vm.createSelectFork(rpc);
        require(block.chainid == KITE_TESTNET_CHAIN_ID, "must fork Kite testnet (2368)");

        string memory raw = vm.readFile(DEPLOYMENTS_FILE);
        usdc = vm.parseJsonAddress(raw, ".addresses.usdc");
        swapRouter = vm.parseJsonAddress(raw, ".addresses.swapRouter");
        strategyRegistry = vm.parseJsonAddress(raw, ".addresses.strategyRegistry");
        allocatorVault = vm.parseJsonAddress(raw, ".addresses.allocatorVault");
        userVault = vm.parseJsonAddress(raw, ".addresses.userVault");
        tav = vm.parseJsonAddress(raw, ".addresses.tradeAttestationVerifier");
        priceAnchor = vm.parseJsonAddress(raw, ".addresses.oraclePriceAnchor");
        yieldAnchor = vm.parseJsonAddress(raw, ".addresses.oracleYieldAnchor");
        legacyMomentum = vm.parseJsonAddress(raw, ".addresses.strategyVaultMomentum");
        legacyMeanReversion = vm.parseJsonAddress(raw, ".addresses.strategyVaultMeanReversion");
        legacyYieldRotation = vm.parseJsonAddress(raw, ".addresses.strategyVaultYieldRotation");

        vaultsOwner = IOwnable(userVault).owner();
        require(
            vaultsOwner == IOwnable(allocatorVault).owner(),
            "UserVault and AllocatorVault owners must match"
        );
    }

    /// Snapshot: confirm the gap actually exists on the forked state.
    /// If this passes false, the upgrades were already executed
    /// out-of-band and the rest of the suite is moot.
    function test_PreUpgradeGapExists() public view {
        (bool okUserPaused,) = userVault.staticcall(abi.encodeWithSignature("paused()"));
        assertFalse(okUserPaused, "UserVault.paused() should revert pre-upgrade");

        (bool okAllocPaused,) = allocatorVault.staticcall(abi.encodeWithSignature("paused()"));
        assertFalse(okAllocPaused, "AllocatorVault.paused() should revert pre-upgrade");

        (bool okUTD,) = allocatorVault.staticcall(
            abi.encodeWithSignature("userTotalDeployed(address)", address(0))
        );
        assertFalse(okUTD, "AllocatorVault.userTotalDeployed() should revert pre-upgrade");
    }

    /// Unit 1 — UserVault + AllocatorVault impl swap.
    /// Mirrors UpgradeUserAndAllocatorVaults.run() under the on-chain owner.
    function test_UpgradeUserAndAllocatorVaults() public {
        UserVault uvImpl = new UserVault();
        AllocatorVault avImpl = new AllocatorVault();

        vm.startPrank(vaultsOwner);
        IUUPS(userVault).upgradeToAndCall(address(uvImpl), "");
        IUUPS(allocatorVault).upgradeToAndCall(address(avImpl), "");
        vm.stopPrank();

        // EIP-1967 impl slot points to the new impls.
        assertEq(_implOf(userVault), address(uvImpl), "UserVault impl slot");
        assertEq(_implOf(allocatorVault), address(avImpl), "AllocatorVault impl slot");

        // UserVault Pausable mixin live.
        assertFalse(UserVault(userVault).paused(), "UserVault initial paused");
        vm.prank(vaultsOwner);
        UserVault(userVault).pause();
        assertTrue(UserVault(userVault).paused(), "UserVault.pause()");
        vm.prank(vaultsOwner);
        UserVault(userVault).unpause();
        assertFalse(UserVault(userVault).paused(), "UserVault.unpause()");

        // AllocatorVault Pausable mixin live.
        assertFalse(AllocatorVault(allocatorVault).paused(), "AllocatorVault initial paused");
        vm.prank(vaultsOwner);
        AllocatorVault(allocatorVault).pause();
        assertTrue(AllocatorVault(allocatorVault).paused(), "AllocatorVault.pause()");
        vm.prank(vaultsOwner);
        AllocatorVault(allocatorVault).unpause();

        // userTotalDeployed view callable post-upgrade.
        assertEq(
            AllocatorVault(allocatorVault).userTotalDeployed(address(0)),
            0,
            "userTotalDeployed for zero address"
        );

        // Non-owner cannot pause (sanity on access control).
        vm.expectRevert();
        UserVault(userVault).pause();
        vm.expectRevert();
        AllocatorVault(allocatorVault).pause();
    }

    /// Unit 2 — base trio fresh deploy via the script's runWith(Inputs).
    /// In test context, vm.startBroadcast(pk) just pranks as vm.addr(pk),
    /// so a synthetic deployer key + dealt USDC suffices. We stage a copy
    /// of kite-testnet.json so the script's _patchJson can't clobber the
    /// real deployment file.
    function test_RedeployBaseTrio() public {
        // Stage fixture so _patchJson touches a throwaway file.
        vm.writeFile(TEST_FILE, vm.readFile(DEPLOYMENTS_FILE));

        uint256 syntheticPk = 0xB0BCAFE;
        address syntheticDeployer = vm.addr(syntheticPk);

        // 3 strategies × 5k USDC stake = 15k; over-fund to be safe.
        deal(usdc, syntheticDeployer, 100_000e6);

        RedeployBaseTrioStrategyVaults script = new RedeployBaseTrioStrategyVaults();
        RedeployBaseTrioStrategyVaults.Inputs memory inputs = RedeployBaseTrioStrategyVaults.Inputs({
            deployerPk: syntheticPk,
            usdc: usdc,
            strategyRegistry: strategyRegistry,
            allocatorVault: allocatorVault,
            tradeVerifier: tav,
            swapRouter: swapRouter,
            oraclePriceAnchor: priceAnchor,
            oracleYieldAnchor: yieldAnchor,
            outLabel: TEST_LABEL
        });
        RedeployBaseTrioStrategyVaults.BaseTrioAddresses memory v = script.runWith(inputs);

        // Fresh proxies deployed.
        assertTrue(v.strategyVaultMomentum != address(0), "mom proxy non-zero");
        assertTrue(v.strategyVaultMeanReversion != address(0), "mr proxy non-zero");
        assertTrue(v.strategyVaultYieldRotation != address(0), "yr proxy non-zero");
        assertTrue(v.strategyVaultMomentum != legacyMomentum, "mom != legacy proxy");
        assertTrue(v.strategyVaultMeanReversion != legacyMeanReversion, "mr != legacy proxy");
        assertTrue(v.strategyVaultYieldRotation != legacyYieldRotation, "yr != legacy proxy");

        // All three on the same fresh impl (one impl deploy per class is the
        // script's behavior — they're three distinct impls but with identical
        // bytecode and identical anchors). Just assert each impl slot is non-zero.
        assertTrue(_implOf(v.strategyVaultMomentum) != address(0), "mom impl set");
        assertTrue(_implOf(v.strategyVaultMeanReversion) != address(0), "mr impl set");
        assertTrue(_implOf(v.strategyVaultYieldRotation) != address(0), "yr impl set");

        // Registered + active.
        StrategyRegistry sr = StrategyRegistry(strategyRegistry);
        assertTrue(sr.strategyOf(v.strategyVaultMomentum).active, "mom active");
        assertTrue(sr.strategyOf(v.strategyVaultMeanReversion).active, "mr active");
        assertTrue(sr.strategyOf(v.strategyVaultYieldRotation).active, "yr active");
        // Legacy entries deliberately preserved.
        assertTrue(sr.strategyOf(legacyMomentum).active, "legacy mom still registered");
        assertTrue(sr.strategyOf(legacyMeanReversion).active, "legacy mr still registered");
        assertTrue(sr.strategyOf(legacyYieldRotation).active, "legacy yr still registered");

        // Phase-3 impl: paused() callable.
        assertFalse(StrategyVault(v.strategyVaultMomentum).paused(), "mom paused initial");
        assertFalse(StrategyVault(v.strategyVaultMeanReversion).paused(), "mr paused initial");
        assertFalse(StrategyVault(v.strategyVaultYieldRotation).paused(), "yr paused initial");

        // Manifest carries the redeploy paramsHash.
        assertEq(
            StrategyVault(v.strategyVaultMomentum).manifest().paramsHash,
            keccak256("helios.mom_v1.base.phase3-redeploy"),
            "mom paramsHash"
        );
        assertEq(
            StrategyVault(v.strategyVaultMeanReversion).manifest().paramsHash,
            keccak256("helios.mr_v1.base.phase3-redeploy"),
            "mr paramsHash"
        );
        assertEq(
            StrategyVault(v.strategyVaultYieldRotation).manifest().paramsHash,
            keccak256("helios.yr_v1.base.phase3-redeploy"),
            "yr paramsHash"
        );

        // JSON merge: base trio keys overwritten with new addresses, all
        // other keys preserved, fresh timestamp stamped.
        string memory written = vm.readFile(TEST_FILE);
        string memory original = vm.readFile(DEPLOYMENTS_FILE);

        assertEq(
            vm.parseJsonAddress(written, ".addresses.strategyVaultMomentum"),
            v.strategyVaultMomentum,
            "json mom overwrite"
        );
        assertEq(
            vm.parseJsonAddress(written, ".addresses.strategyVaultMeanReversion"),
            v.strategyVaultMeanReversion,
            "json mr overwrite"
        );
        assertEq(
            vm.parseJsonAddress(written, ".addresses.strategyVaultYieldRotation"),
            v.strategyVaultYieldRotation,
            "json yr overwrite"
        );
        // Variant2 + Variant3 + oracle anchors etc. preserved.
        assertEq(
            vm.parseJsonAddress(written, ".addresses.strategyVaultMomentumVariant2"),
            vm.parseJsonAddress(original, ".addresses.strategyVaultMomentumVariant2"),
            "variant2 preserved"
        );
        assertEq(
            vm.parseJsonAddress(written, ".addresses.strategyVaultYieldRotationVariant3"),
            vm.parseJsonAddress(original, ".addresses.strategyVaultYieldRotationVariant3"),
            "variant3 preserved"
        );
        assertEq(
            vm.parseJsonAddress(written, ".addresses.oraclePriceAnchor"),
            vm.parseJsonAddress(original, ".addresses.oraclePriceAnchor"),
            "oracle preserved"
        );
        assertEq(
            vm.parseJsonAddress(written, ".addresses.tradeAttestationVerifier"),
            vm.parseJsonAddress(original, ".addresses.tradeAttestationVerifier"),
            "tav preserved"
        );

        assertGt(
            vm.parseJsonUint(written, ".phase3BaseTrioRedeployedAt"),
            0,
            "phase3BaseTrioRedeployedAt timestamp set"
        );
    }

    function _implOf(address proxy) internal view returns (address) {
        bytes32 raw = vm.load(proxy, EIP1967_IMPL_SLOT);
        return address(uint160(uint256(raw)));
    }
}
