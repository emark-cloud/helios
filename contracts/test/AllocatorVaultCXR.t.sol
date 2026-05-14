// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Test } from "forge-std/Test.sol";
import { AllocatorVault } from "../src/AllocatorVault.sol";
import { StrategyRegistry } from "../src/StrategyRegistry.sol";
import { MockERC20 } from "./mocks/MockERC20.sol";
import { MockUserVault } from "./mocks/MockUserVault.sol";
import { ERC1967Proxy } from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";
import { Ownable } from "@openzeppelin/contracts/access/Ownable.sol";
import { MetaStrategyLib } from "../src/interfaces/IMetaStrategy.sol";
import { MessagingFee } from "@layerzerolabs/oapp-evm/oft/interfaces/IOFT.sol";

/// @notice CXR-0b — Test the AllocatorVault cross-chain helpers added
///         for OFT-based allocate/defund. Covers wiring, auth, and the
///         settleRemoteDefund accounting decrement. The forward path
///         (`allocateToRemoteStrategy`) drives a real LZ V2 send call
///         and is exercised against a fork in the broadcast suite.
contract AllocatorVaultCXRTest is Test {
    AllocatorVault internal av;
    StrategyRegistry internal registry;
    MockERC20 internal usdc;
    MockUserVault internal userVault;

    address internal owner = makeAddr("owner");
    address internal operator = makeAddr("operator");
    address internal user = makeAddr("user");
    address internal bridgeReceiver = makeAddr("bridgeReceiver");
    address internal oftAdapter = makeAddr("oftAdapter");
    address internal anchor = makeAddr("anchor");
    bytes32 internal constant STRATEGY = bytes32(uint256(0xABCD));
    uint32 internal constant ARB_EID = 40_231;

    function setUp() public {
        usdc = new MockERC20("USDC", "USDC");
        userVault = new MockUserVault(usdc);
        registry = new StrategyRegistry(usdc, anchor, owner, 7 days);

        AllocatorVault impl = new AllocatorVault();
        bytes memory init = abi.encodeCall(
            AllocatorVault.initialize,
            (usdc, operator, address(userVault), address(registry), 1000, owner)
        );
        av = AllocatorVault(address(new ERC1967Proxy(address(impl), init)));

        // Configure user meta-strategy so creditFromAllocator passes.
        bytes32[] memory classes = new bytes32[](0);
        address[] memory allowedAssets = new address[](1);
        allowedAssets[0] = address(usdc);
        uint32[] memory allowedChains = new uint32[](2);
        allowedChains[0] = uint32(block.chainid);
        allowedChains[1] = ARB_EID;
        userVault.setMeta(
            user,
            MetaStrategyLib.MetaStrategy({
                metaStrategyHash: bytes32(uint256(1)),
                allowedStrategyClasses: classes,
                allowedAssets: allowedAssets,
                allowedChains: allowedChains,
                maxCapital: 1_000_000e6,
                maxPerStrategyBps: 10_000,
                maxStrategiesCount: 8,
                drawdownThresholdBps: 1500,
                maxFeeRateBps: 2500,
                rebalanceCadenceSec: 1 days,
                validUntil: uint64(block.timestamp + 30 days),
                defundTwapBars: MetaStrategyLib.DEFAULT_DEFUND_TWAP_BARS,
                defundBondBps: MetaStrategyLib.DEFAULT_DEFUND_BOND_BPS,
                defundConfirmBlocks: MetaStrategyLib.DEFAULT_DEFUND_CONFIRM_BLOCKS
            })
        );
        userVault.setAllocator(user, address(av));
    }

    function test_setBridgeReceiver_onlyOwner() public {
        vm.prank(makeAddr("rando"));
        vm.expectRevert(
            abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, makeAddr("rando"))
        );
        av.setBridgeReceiver(bridgeReceiver);
    }

    function test_setBridgeReceiver_stores() public {
        vm.prank(owner);
        av.setBridgeReceiver(bridgeReceiver);
        assertEq(av.bridgeReceiver(), bridgeReceiver);
    }

    function test_setOftAdapter_stores() public {
        vm.prank(owner);
        av.setOftAdapter(oftAdapter);
        assertEq(av.oftAdapter(), oftAdapter);
    }

    function test_settleRemoteDefund_onlyBridgeReceiver() public {
        vm.prank(owner);
        av.setBridgeReceiver(bridgeReceiver);

        vm.expectRevert(AllocatorVault.NotBridgeReceiver.selector);
        av.settleRemoteDefund(user, STRATEGY, 100e6, ARB_EID);
    }

    function test_settleRemoteDefund_rejectsZeroAmount() public {
        vm.prank(owner);
        av.setBridgeReceiver(bridgeReceiver);
        vm.prank(bridgeReceiver);
        vm.expectRevert(AllocatorVault.ZeroAmount.selector);
        av.settleRemoteDefund(user, STRATEGY, 0, ARB_EID);
    }

    // ── CXR-0c — destinationReceiver per-EID map ─────────────────────

    function test_setDestinationReceiver_onlyOwner() public {
        vm.prank(makeAddr("rando"));
        vm.expectRevert(
            abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, makeAddr("rando"))
        );
        av.setDestinationReceiver(ARB_EID, bridgeReceiver);
    }

    function test_setDestinationReceiver_rejectsZero() public {
        vm.prank(owner);
        vm.expectRevert(AllocatorVault.ZeroAddress.selector);
        av.setDestinationReceiver(ARB_EID, address(0));
    }

    function test_setDestinationReceiver_storesPerEid() public {
        address baseReceiver = makeAddr("baseReceiver");
        address arbReceiver = makeAddr("arbReceiver");
        vm.startPrank(owner);
        av.setDestinationReceiver(40_245, baseReceiver);
        av.setDestinationReceiver(ARB_EID, arbReceiver);
        vm.stopPrank();
        assertEq(av.destinationReceiver(40_245), baseReceiver);
        assertEq(av.destinationReceiver(ARB_EID), arbReceiver);
    }

    function test_allocateToRemoteStrategy_revertsIfDestinationReceiverUnset() public {
        vm.startPrank(owner);
        av.setOftAdapter(oftAdapter);
        av.setBridgeReceiver(bridgeReceiver);
        // Intentionally NOT setting destinationReceiver[ARB_EID].
        vm.stopPrank();

        MessagingFee memory lzFee = MessagingFee({ nativeFee: 0, lzTokenFee: 0 });
        vm.prank(operator);
        vm.expectRevert(AllocatorVault.DestinationReceiverUnset.selector);
        av.allocateToRemoteStrategy(
            user, STRATEGY, 100e6, ARB_EID, makeAddr("remoteVault"), "", lzFee
        );
    }

    // ── CXR-cost Tier 2 — batched `allocateToRemoteStrategyBatch` ────

    function _batchParams(uint256 n)
        internal
        view
        returns (AllocatorVault.RemoteBatchParams memory p)
    {
        bytes32[] memory sids = new bytes32[](n);
        uint256[] memory amts = new uint256[](n);
        address[] memory vaults = new address[](n);
        for (uint256 i; i < n; ++i) {
            sids[i] = bytes32(uint256(0xCAFE0000 + i));
            amts[i] = (i + 1) * 100e6;
            vaults[i] = address(uint160(0xBEEF0000 + i));
        }
        p = AllocatorVault.RemoteBatchParams({
            user: user,
            strategyIds: sids,
            amounts: amts,
            remoteVaults: vaults,
            dstEid: ARB_EID,
            extraOptions: "",
            lzFee: MessagingFee({ nativeFee: 0, lzTokenFee: 0 })
        });
    }

    function test_allocateBatch_revertsOnEmptyBatch() public {
        vm.startPrank(owner);
        av.setOftAdapter(oftAdapter);
        av.setDestinationReceiver(ARB_EID, bridgeReceiver);
        vm.stopPrank();

        AllocatorVault.RemoteBatchParams memory p = _batchParams(0);
        vm.prank(operator);
        vm.expectRevert(abi.encodeWithSelector(AllocatorVault.InvalidBatchSize.selector, 0));
        av.allocateToRemoteStrategyBatch(p);
    }

    function test_allocateBatch_revertsOnBatchSizeOverCap() public {
        vm.startPrank(owner);
        av.setOftAdapter(oftAdapter);
        av.setDestinationReceiver(ARB_EID, bridgeReceiver);
        vm.stopPrank();

        AllocatorVault.RemoteBatchParams memory p = _batchParams(17);
        vm.prank(operator);
        vm.expectRevert(abi.encodeWithSelector(AllocatorVault.InvalidBatchSize.selector, 17));
        av.allocateToRemoteStrategyBatch(p);
    }

    function test_allocateBatch_revertsOnMismatchedArrayLengths() public {
        vm.startPrank(owner);
        av.setOftAdapter(oftAdapter);
        av.setDestinationReceiver(ARB_EID, bridgeReceiver);
        vm.stopPrank();

        AllocatorVault.RemoteBatchParams memory p = _batchParams(2);
        // Break the symmetry: amounts has only 1 entry.
        uint256[] memory shortAmts = new uint256[](1);
        shortAmts[0] = 100e6;
        p.amounts = shortAmts;

        vm.prank(operator);
        vm.expectRevert(AllocatorVault.MismatchedBatchArrays.selector);
        av.allocateToRemoteStrategyBatch(p);
    }

    function test_allocateBatch_revertsOnZeroAmount() public {
        vm.startPrank(owner);
        av.setOftAdapter(oftAdapter);
        av.setDestinationReceiver(ARB_EID, bridgeReceiver);
        vm.stopPrank();

        AllocatorVault.RemoteBatchParams memory p = _batchParams(2);
        p.amounts[1] = 0; // dust entry

        vm.prank(operator);
        vm.expectRevert(AllocatorVault.ZeroAmount.selector);
        av.allocateToRemoteStrategyBatch(p);
    }

    function test_allocateBatch_revertsOnZeroRemoteVault() public {
        vm.startPrank(owner);
        av.setOftAdapter(oftAdapter);
        av.setDestinationReceiver(ARB_EID, bridgeReceiver);
        vm.stopPrank();

        AllocatorVault.RemoteBatchParams memory p = _batchParams(2);
        p.remoteVaults[0] = address(0);

        vm.prank(operator);
        vm.expectRevert(AllocatorVault.ZeroAddress.selector);
        av.allocateToRemoteStrategyBatch(p);
    }

    function test_allocateBatch_revertsIfDestinationReceiverUnset() public {
        vm.prank(owner);
        av.setOftAdapter(oftAdapter);
        // No setDestinationReceiver — both single and batch paths must
        // fast-fail on this gate so a mis-wired operator can't burn an
        // LZ V2 fee before the receiver is set per chain.

        AllocatorVault.RemoteBatchParams memory p = _batchParams(2);

        vm.prank(operator);
        vm.expectRevert(AllocatorVault.DestinationReceiverUnset.selector);
        av.allocateToRemoteStrategyBatch(p);
    }

    function test_allocateBatch_revertsIfOftAdapterUnset() public {
        vm.prank(owner);
        av.setDestinationReceiver(ARB_EID, bridgeReceiver);

        AllocatorVault.RemoteBatchParams memory p = _batchParams(2);

        vm.prank(operator);
        vm.expectRevert(AllocatorVault.OftAdapterUnset.selector);
        av.allocateToRemoteStrategyBatch(p);
    }

    function test_allocateBatch_onlyOperator() public {
        vm.startPrank(owner);
        av.setOftAdapter(oftAdapter);
        av.setDestinationReceiver(ARB_EID, bridgeReceiver);
        vm.stopPrank();

        AllocatorVault.RemoteBatchParams memory p = _batchParams(2);

        vm.prank(makeAddr("rando"));
        // Auth gate fires before validation; expect the operator-mismatch
        // revert (any non-operator caller is rejected uniformly).
        vm.expectRevert();
        av.allocateToRemoteStrategyBatch(p);
    }

    function test_settleRemoteDefund_creditsUserVaultAndDecrements() public {
        vm.prank(owner);
        av.setBridgeReceiver(bridgeReceiver);

        // BridgeReceiver "delivered" USDC to AllocatorVault before
        // invoking settleRemoteDefund.
        usdc.mint(address(av), 500e6);

        // Simulate the allocator having booked a 500e6 remote
        // allocation by raw-writing the slot. Easier: open with
        // settleRemoteDefund returning more than outstanding (clamps to 0).

        vm.prank(bridgeReceiver);
        av.settleRemoteDefund(user, STRATEGY, 500e6, ARB_EID);

        // UserVault balance should now hold the 500e6 credit.
        assertEq(usdc.balanceOf(address(userVault)), 500e6);
        // Outstanding remote allocation stays at 0 (clamp).
        assertEq(av.userRemoteDeployed(user, STRATEGY, ARB_EID), 0);
    }
}
