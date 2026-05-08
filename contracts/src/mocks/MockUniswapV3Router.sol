// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { IERC20 } from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import { SafeERC20 } from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import { Ownable } from "@openzeppelin/contracts/access/Ownable.sol";

/// @notice Uniswap-V3-shape SwapRouter02 stand-in for testnet fallbacks.
///         Mimics `exactInputSingle` so the SDK ships identical calldata
///         against the real Uniswap V3 router on Base Sepolia and against
///         this mock — only `swapRouter` vs `mockSwapRouter` in the
///         deployment JSON differs. Holds its own inventory of each output
///         asset (admin-funded) and applies a fixed admin-set price per
///         (tokenIn, tokenOut, fee) tuple. The `fee` axis is included so
///         multi-tier strategies (USDC.5bps vs USDC.30bps) can be modeled.
///
///         phase5-plan.md §WS2.
contract MockUniswapV3Router is Ownable {
    using SafeERC20 for IERC20;

    struct ExactInputSingleParams {
        address tokenIn;
        address tokenOut;
        uint24 fee;
        address recipient;
        uint256 deadline;
        uint256 amountIn;
        uint256 amountOutMinimum;
        uint160 sqrtPriceLimitX96; // unused
    }

    struct Price {
        uint256 num;
        uint256 denom;
    }

    mapping(address tokenIn => mapping(address tokenOut => mapping(uint24 fee => Price))) internal
        _price;

    error PriceNotSet();
    error DeadlinePassed();
    error TooLittleReceived();
    error InsufficientLiquidity();

    event PriceSet(
        address indexed tokenIn,
        address indexed tokenOut,
        uint24 indexed fee,
        uint256 num,
        uint256 denom
    );
    event Swapped(
        address indexed payer,
        address indexed recipient,
        address indexed tokenIn,
        address tokenOut,
        uint24 fee,
        uint256 amountIn,
        uint256 amountOut
    );

    constructor(address owner_) Ownable(owner_) { }

    function setPrice(address tokenIn, address tokenOut, uint24 fee, uint256 num, uint256 denom)
        external
        onlyOwner
    {
        require(num > 0 && denom > 0, "MockUniswapV3Router: bad price");
        _price[tokenIn][tokenOut][fee] = Price({ num: num, denom: denom });
        emit PriceSet(tokenIn, tokenOut, fee, num, denom);
    }

    function priceOf(address tokenIn, address tokenOut, uint24 fee)
        external
        view
        returns (Price memory)
    {
        return _price[tokenIn][tokenOut][fee];
    }

    function exactInputSingle(ExactInputSingleParams calldata params)
        external
        returns (uint256 amountOut)
    {
        if (block.timestamp > params.deadline) revert DeadlinePassed();
        Price memory p = _price[params.tokenIn][params.tokenOut][params.fee];
        if (p.denom == 0) revert PriceNotSet();

        amountOut = (params.amountIn * p.num) / p.denom;
        if (amountOut < params.amountOutMinimum) revert TooLittleReceived();
        if (IERC20(params.tokenOut).balanceOf(address(this)) < amountOut) {
            revert InsufficientLiquidity();
        }

        IERC20(params.tokenIn).safeTransferFrom(msg.sender, address(this), params.amountIn);
        IERC20(params.tokenOut).safeTransfer(params.recipient, amountOut);

        emit Swapped(
            msg.sender,
            params.recipient,
            params.tokenIn,
            params.tokenOut,
            params.fee,
            params.amountIn,
            amountOut
        );
    }
}
