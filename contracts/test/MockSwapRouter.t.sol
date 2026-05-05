// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Test } from "forge-std/Test.sol";
import { MockSwapRouter } from "./mocks/MockSwapRouter.sol";
import { MockERC20 } from "./mocks/MockERC20.sol";
import { Ownable } from "@openzeppelin/contracts/access/Ownable.sol";

contract MockSwapRouterTest is Test {
    MockSwapRouter internal router;
    MockERC20 internal usdc;
    MockERC20 internal eth;

    address internal owner = makeAddr("owner");
    address internal trader = makeAddr("trader");

    function setUp() public {
        usdc = new MockERC20("USDC", "USDC");
        eth = new MockERC20("ETH", "ETH");
        router = new MockSwapRouter(owner);

        // 1 USDC (1e6) → 0.0005 ETH (5e14): num=5e14, denom=1e6 → 5e8 per unit USDC
        // For 1000 USDC (1000e6), amountOut = 1000e6 * 5e14 / 1e6 = 5e17 = 0.5 ETH
        vm.prank(owner);
        router.setPrice(address(usdc), address(eth), 5e14, 1e6);

        // Pre-fund router with ETH so it can pay out.
        eth.mint(address(router), 1000e18);

        // Trader holds USDC.
        usdc.mint(trader, 10_000e6);
        vm.prank(trader);
        usdc.approve(address(router), type(uint256).max);
    }

    function test_SetPrice_OnlyOwner() public {
        vm.prank(trader);
        vm.expectRevert(abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, trader));
        router.setPrice(address(usdc), address(eth), 1, 1);
    }

    function test_SetPrice_RevertsOnZero() public {
        vm.prank(owner);
        vm.expectRevert(bytes("MockSwapRouter: bad price"));
        router.setPrice(address(usdc), address(eth), 0, 1);
    }

    function test_ExactInputSingle_HappyPath() public {
        MockSwapRouter.ExactInputSingleParams memory p = MockSwapRouter.ExactInputSingleParams({
            tokenIn: address(usdc),
            tokenOut: address(eth),
            recipient: trader,
            deadline: block.timestamp + 60,
            amountIn: 1000e6,
            amountOutMinimum: 4e17,
            limitSqrtPrice: 0
        });
        vm.prank(trader);
        uint256 out = router.exactInputSingle(p);
        assertEq(out, 5e17);
        assertEq(eth.balanceOf(trader), 5e17);
        assertEq(usdc.balanceOf(address(router)), 1000e6);
    }

    function test_ExactInputSingle_RevertsOnDeadline() public {
        MockSwapRouter.ExactInputSingleParams memory p = MockSwapRouter.ExactInputSingleParams({
            tokenIn: address(usdc),
            tokenOut: address(eth),
            recipient: trader,
            deadline: block.timestamp - 1,
            amountIn: 1,
            amountOutMinimum: 0,
            limitSqrtPrice: 0
        });
        vm.prank(trader);
        vm.expectRevert(MockSwapRouter.DeadlinePassed.selector);
        router.exactInputSingle(p);
    }

    function test_ExactInputSingle_RevertsOnUnknownPair() public {
        MockSwapRouter.ExactInputSingleParams memory p = MockSwapRouter.ExactInputSingleParams({
            tokenIn: address(eth),
            tokenOut: address(usdc),
            recipient: trader,
            deadline: block.timestamp + 60,
            amountIn: 1,
            amountOutMinimum: 0,
            limitSqrtPrice: 0
        });
        vm.prank(trader);
        vm.expectRevert(MockSwapRouter.PriceNotSet.selector);
        router.exactInputSingle(p);
    }

    function test_ExactInputSingle_RevertsOnSlippage() public {
        MockSwapRouter.ExactInputSingleParams memory p = MockSwapRouter.ExactInputSingleParams({
            tokenIn: address(usdc),
            tokenOut: address(eth),
            recipient: trader,
            deadline: block.timestamp + 60,
            amountIn: 1000e6,
            amountOutMinimum: 1e18, // demand 1 ETH but only get 0.5
            limitSqrtPrice: 0
        });
        vm.prank(trader);
        vm.expectRevert(MockSwapRouter.TooLittleReceived.selector);
        router.exactInputSingle(p);
    }

    function test_ExactInputSingle_RevertsOnInsufficientLiquidity() public {
        // Drain router ETH then attempt swap.
        vm.prank(address(router));
        eth.transfer(makeAddr("sink"), 1000e18);

        MockSwapRouter.ExactInputSingleParams memory p = MockSwapRouter.ExactInputSingleParams({
            tokenIn: address(usdc),
            tokenOut: address(eth),
            recipient: trader,
            deadline: block.timestamp + 60,
            amountIn: 1000e6,
            amountOutMinimum: 0,
            limitSqrtPrice: 0
        });
        vm.prank(trader);
        vm.expectRevert(MockSwapRouter.InsufficientLiquidity.selector);
        router.exactInputSingle(p);
    }
}
