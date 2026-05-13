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
        usdc.mint(address(receiver), 1_000e6);

        bytes memory msgData = _composeMessage(
            1, 40231, 1_000e6, 0 /*ALLOCATE*/, bytes32(uint256(0xABCD)), address(vault), user
        );

        vm.prank(endpoint);
        receiver.lzCompose(oftAdapter, bytes32(0), msgData, address(0), "");

        assertEq(usdc.balanceOf(address(vault)), 1_000e6, "vault should hold released usdc");
        assertEq(vault.lastAmount(), 1_000e6, "vault.onCrossChainAllocate should fire");
        assertEq(vault.lastUser(), user);
    }

    function test_allocate_revertingVaultParksFunds() public {
        usdc.mint(address(receiver), 500e6);
        vault.setShouldRevert(true);

        bytes memory msgData = _composeMessage(
            1, 40231, 500e6, 0, bytes32(uint256(0xABCD)), address(vault), user
        );

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
            40231,
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
        assertEq(allocator.lastSrcEid(), 40231);
    }

    function test_rejectsNonEndpoint() public {
        bytes memory msgData = _composeMessage(
            1, 40231, 1e6, 0, bytes32(uint256(0x1)), address(vault), user
        );
        vm.expectRevert(HeliosBridgeReceiver.NotEndpoint.selector);
        receiver.lzCompose(oftAdapter, bytes32(0), msgData, address(0), "");
    }

    function test_rejectsUntrustedFrom() public {
        bytes memory msgData = _composeMessage(
            1, 40231, 1e6, 0, bytes32(uint256(0x1)), address(vault), user
        );
        vm.prank(endpoint);
        vm.expectRevert(HeliosBridgeReceiver.UntrustedComposeFrom.selector);
        receiver.lzCompose(address(0xBAD), bytes32(0), msgData, address(0), "");
    }
}
