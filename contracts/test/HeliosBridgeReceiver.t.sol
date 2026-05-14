// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Test } from "forge-std/Test.sol";
import { HeliosBridgeReceiver } from "../src/HeliosBridgeReceiver.sol";
import { OFTComposeMsgCodec } from "@layerzerolabs/oapp-evm/oft/libs/OFTComposeMsgCodec.sol";
import { ERC20Mock } from "@openzeppelin/contracts/mocks/token/ERC20Mock.sol";

contract MockStrategyVault {
    uint256 public lastAmount;
    address public lastUser;
    bool public shouldRevert;

    function onCrossChainAllocate(uint256 amount, address user) external {
        if (shouldRevert) revert("vault refused");
        lastAmount = amount;
        lastUser = user;
    }

    function setShouldRevert(bool v) external {
        shouldRevert = v;
    }
}

contract MockAllocatorVault {
    address public lastUser;
    bytes32 public lastStrategy;
    uint256 public lastAmount;
    uint32 public lastSrcEid;

    function settleRemoteDefund(address user, bytes32 strategyId, uint256 amount, uint32 srcEid)
        external
    {
        lastUser = user;
        lastStrategy = strategyId;
        lastAmount = amount;
        lastSrcEid = srcEid;
    }
}

contract HeliosBridgeReceiverTest is Test {
    HeliosBridgeReceiver internal receiver;
    ERC20Mock internal usdc;
    MockStrategyVault internal vault;
    MockAllocatorVault internal allocator;

    address internal endpoint = address(0xE);
    address internal oftAdapter = address(0xA);
    address internal owner = address(0xC0FFEE);
    address internal user = address(0xBEEF);

    function setUp() public {
        usdc = new ERC20Mock();
        vault = new MockStrategyVault();
        allocator = new MockAllocatorVault();
        receiver = new HeliosBridgeReceiver(address(usdc), endpoint, oftAdapter, owner);
        vm.prank(owner);
        receiver.setAllocatorVault(address(allocator));
    }

    function _composeMessage(
        uint64 nonce,
        uint32 srcEid,
        uint256 amount,
        uint8 action,
        bytes32 strategyId,
        address remoteVault,
        address u
    ) internal pure returns (bytes memory) {
        bytes memory inner = abi.encode(action, strategyId, remoteVault, u);
        // composeFrom = padded address(0) for the test; codec needs the
        // 32-byte composeFrom prefix before our inner payload.
        bytes memory composeFromPlusInner = bytes.concat(bytes32(0), inner);
        return OFTComposeMsgCodec.encode(nonce, srcEid, amount, composeFromPlusInner);
    }

    function test_allocate_pathReleasesUsdcAndCallsVault() public {
        // Bridge holds released USDC (simulating prior _credit step).
        usdc.mint(address(receiver), 1000e6);

        bytes memory msgData = _composeMessage(
            1,
            40_231,
            1000e6,
            0,
            /*ALLOCATE*/
            bytes32(uint256(0xABCD)),
            address(vault),
            user
        );

        vm.prank(endpoint);
        receiver.lzCompose(oftAdapter, bytes32(0), msgData, address(0), "");

        assertEq(usdc.balanceOf(address(vault)), 1000e6, "vault should hold released usdc");
        assertEq(vault.lastAmount(), 1000e6, "vault.onCrossChainAllocate should fire");
        assertEq(vault.lastUser(), user);
    }

    function test_allocate_revertingVaultParksFunds() public {
        usdc.mint(address(receiver), 500e6);
        vault.setShouldRevert(true);

        bytes memory msgData =
            _composeMessage(1, 40_231, 500e6, 0, bytes32(uint256(0xABCD)), address(vault), user);

        vm.prank(endpoint);
        receiver.lzCompose(oftAdapter, bytes32(0), msgData, address(0), "");

        // USDC has already moved to vault (safeTransfer); the catch
        // path still parks the user's recoverable balance so the
        // operator can move funds back manually.
        assertEq(receiver.recoverable(user), 500e6, "should park recoverable");
    }

    function test_defundPath_creditsAllocatorVault() public {
        usdc.mint(address(receiver), 250e6);

        bytes memory msgData = _composeMessage(
            42,
            40_231,
            250e6,
            1, /*SETTLE_DEFUND*/
            bytes32(uint256(0xDEAD)),
            address(0),
            user
        );

        vm.prank(endpoint);
        receiver.lzCompose(oftAdapter, bytes32(0), msgData, address(0), "");

        assertEq(usdc.balanceOf(address(allocator)), 250e6);
        assertEq(allocator.lastUser(), user);
        assertEq(allocator.lastStrategy(), bytes32(uint256(0xDEAD)));
        assertEq(allocator.lastAmount(), 250e6);
        assertEq(allocator.lastSrcEid(), 40_231);
    }

    function test_rejectsNonEndpoint() public {
        bytes memory msgData =
            _composeMessage(1, 40_231, 1e6, 0, bytes32(uint256(0x1)), address(vault), user);
        vm.expectRevert(HeliosBridgeReceiver.NotEndpoint.selector);
        receiver.lzCompose(oftAdapter, bytes32(0), msgData, address(0), "");
    }

    function test_rejectsUntrustedFrom() public {
        bytes memory msgData =
            _composeMessage(1, 40_231, 1e6, 0, bytes32(uint256(0x1)), address(vault), user);
        vm.prank(endpoint);
        vm.expectRevert(HeliosBridgeReceiver.UntrustedComposeFrom.selector);
        receiver.lzCompose(address(0xBAD), bytes32(0), msgData, address(0), "");
    }

    // ── CXR-cost Tier 2 — batched ALLOCATE shape ─────────────────────

    function _composeBatchMessage(
        uint64 nonce,
        uint32 srcEid,
        uint256 totalAmount,
        bytes32[] memory strategyIds,
        uint256[] memory amounts,
        address[] memory remoteVaults,
        address u
    ) internal pure returns (bytes memory) {
        bytes memory inner = abi.encode(
            uint8(2), /*ACTION_ALLOCATE_BATCH*/
            strategyIds,
            amounts,
            remoteVaults,
            u
        );
        bytes memory composeFromPlusInner = bytes.concat(bytes32(0), inner);
        return OFTComposeMsgCodec.encode(nonce, srcEid, totalAmount, composeFromPlusInner);
    }

    function test_batchAllocate_dispatchesToEachVault() public {
        // Two strategy vaults on the same destination chain; one
        // batched compose should dispatch to both with their respective
        // per-entry amounts. This is the §12.1 mom.base + mr.base
        // scenario.
        MockStrategyVault vaultA = new MockStrategyVault();
        MockStrategyVault vaultB = new MockStrategyVault();

        usdc.mint(address(receiver), 600e6);

        bytes32[] memory sids = new bytes32[](2);
        sids[0] = bytes32(uint256(0xAAAA));
        sids[1] = bytes32(uint256(0xBBBB));
        uint256[] memory amts = new uint256[](2);
        amts[0] = 400e6;
        amts[1] = 200e6;
        address[] memory vaults = new address[](2);
        vaults[0] = address(vaultA);
        vaults[1] = address(vaultB);

        bytes memory msgData = _composeBatchMessage(1, 40_231, 600e6, sids, amts, vaults, user);

        vm.prank(endpoint);
        receiver.lzCompose(oftAdapter, bytes32(0), msgData, address(0), "");

        assertEq(usdc.balanceOf(address(vaultA)), 400e6, "vaultA should hold 400");
        assertEq(usdc.balanceOf(address(vaultB)), 200e6, "vaultB should hold 200");
        assertEq(vaultA.lastAmount(), 400e6);
        assertEq(vaultB.lastAmount(), 200e6);
        assertEq(vaultA.lastUser(), user);
        assertEq(vaultB.lastUser(), user);
        assertEq(receiver.recoverable(user), 0, "no recoverable on happy path");
    }

    function test_batchAllocate_partialFailureRecoversOnlyFailedEntry() public {
        // Three entries; the middle vault reverts. The recoverable
        // pool must hold only the failed entry's amount; the other
        // two settle into their target vaults. Pins the Tier 2 risk:
        // a per-entry revert MUST NOT roll back the whole batch.
        MockStrategyVault vaultA = new MockStrategyVault();
        MockStrategyVault vaultB = new MockStrategyVault();
        MockStrategyVault vaultC = new MockStrategyVault();
        vaultB.setShouldRevert(true);

        usdc.mint(address(receiver), 900e6);

        bytes32[] memory sids = new bytes32[](3);
        sids[0] = bytes32(uint256(0xAAAA));
        sids[1] = bytes32(uint256(0xBBBB));
        sids[2] = bytes32(uint256(0xCCCC));
        uint256[] memory amts = new uint256[](3);
        amts[0] = 300e6;
        amts[1] = 250e6;
        amts[2] = 350e6;
        address[] memory vaults = new address[](3);
        vaults[0] = address(vaultA);
        vaults[1] = address(vaultB);
        vaults[2] = address(vaultC);

        bytes memory msgData = _composeBatchMessage(1, 40_231, 900e6, sids, amts, vaults, user);

        vm.prank(endpoint);
        receiver.lzCompose(oftAdapter, bytes32(0), msgData, address(0), "");

        assertEq(vaultA.lastAmount(), 300e6, "A settled");
        assertEq(vaultC.lastAmount(), 350e6, "C settled");
        // B's USDC moved before the dispatch revert; recoverable
        // pool records the user's claim against the operator-driven
        // recover path.
        assertEq(receiver.recoverable(user), 250e6, "only B parked");
    }

    function test_batchAllocate_revertsOnSumMismatch() public {
        // Sum of per-entry amounts must equal the OFT-credited
        // totalAmountLD. A mismatched payload could otherwise strand
        // capital in the receiver — pin the revert.
        usdc.mint(address(receiver), 500e6);
        bytes32[] memory sids = new bytes32[](2);
        sids[0] = bytes32(uint256(0xAAAA));
        sids[1] = bytes32(uint256(0xBBBB));
        uint256[] memory amts = new uint256[](2);
        amts[0] = 100e6;
        amts[1] = 200e6; // sum = 300, claimed = 500
        address[] memory vaults = new address[](2);
        vaults[0] = address(vault);
        vaults[1] = address(vault);

        bytes memory msgData = _composeBatchMessage(1, 40_231, 500e6, sids, amts, vaults, user);

        vm.prank(endpoint);
        vm.expectRevert(
            abi.encodeWithSelector(
                HeliosBridgeReceiver.BatchAmountMismatch.selector, uint256(300e6), uint256(500e6)
            )
        );
        receiver.lzCompose(oftAdapter, bytes32(0), msgData, address(0), "");
    }

    function test_batchAllocate_revertsOnMismatchedArrays() public {
        usdc.mint(address(receiver), 300e6);
        bytes32[] memory sids = new bytes32[](2);
        sids[0] = bytes32(uint256(0xAAAA));
        sids[1] = bytes32(uint256(0xBBBB));
        uint256[] memory amts = new uint256[](1);
        amts[0] = 300e6;
        address[] memory vaults = new address[](2);
        vaults[0] = address(vault);
        vaults[1] = address(vault);

        bytes memory msgData = _composeBatchMessage(1, 40_231, 300e6, sids, amts, vaults, user);

        vm.prank(endpoint);
        vm.expectRevert(HeliosBridgeReceiver.MismatchedBatchArrays.selector);
        receiver.lzCompose(oftAdapter, bytes32(0), msgData, address(0), "");
    }

    function test_batchAllocate_revertsOnEmptyBatch() public {
        usdc.mint(address(receiver), 0);
        bytes32[] memory sids = new bytes32[](0);
        uint256[] memory amts = new uint256[](0);
        address[] memory vaults = new address[](0);

        bytes memory msgData = _composeBatchMessage(1, 40_231, 0, sids, amts, vaults, user);

        vm.prank(endpoint);
        vm.expectRevert(abi.encodeWithSelector(HeliosBridgeReceiver.InvalidBatchSize.selector, 0));
        receiver.lzCompose(oftAdapter, bytes32(0), msgData, address(0), "");
    }

    function test_batchAllocate_revertsOnBatchSizeOverCap() public {
        // 17 entries > MAX_BATCH_SIZE (16). Sized to a value the
        // receiver will reject before any settlement; mint matching
        // total to isolate the gate.
        uint256 n = 17;
        usdc.mint(address(receiver), n * 1e6);
        bytes32[] memory sids = new bytes32[](n);
        uint256[] memory amts = new uint256[](n);
        address[] memory vaults = new address[](n);
        for (uint256 i; i < n; ++i) {
            sids[i] = bytes32(i);
            amts[i] = 1e6;
            vaults[i] = address(vault);
        }
        bytes memory msgData = _composeBatchMessage(1, 40_231, n * 1e6, sids, amts, vaults, user);

        vm.prank(endpoint);
        vm.expectRevert(abi.encodeWithSelector(HeliosBridgeReceiver.InvalidBatchSize.selector, n));
        receiver.lzCompose(oftAdapter, bytes32(0), msgData, address(0), "");
    }
}
