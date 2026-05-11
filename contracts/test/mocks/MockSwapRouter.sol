// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { IERC20 } from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import { SafeERC20 } from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import { Ownable } from "@openzeppelin/contracts/access/Ownable.sol";

/// @notice Phase-1 swap stand-in. Mimics Algebra Integral's exactInputSingle
///         shape so that StrategyVault.executeWithProof can issue the same
///         calldata it will issue against the real router on Kite mainnet
///         — only the deployed address swaps in. The router holds its own
///         inventory of each output asset (admin-funded) and applies a
///         fixed admin-set price for each (tokenIn, tokenOut) pair.
///
///         When Algebra Integral lands on Kite testnet, swap this router for
///         the real one in the deploy script and StrategyVault.allowedRouter
///         — no other code changes.
contract MockSwapRouter is Ownable {
    using SafeERC20 for IERC20;

    struct ExactInputSingleParams {
        address tokenIn;
        address tokenOut;
        address recipient;
        uint256 deadline;
        uint256 amountIn;
        uint256 amountOutMinimum;
        uint160 limitSqrtPrice; // unused in mock; kept for ABI compat
    }

    /// @dev priceNum / priceDenom of tokenOut per 1 unit of tokenIn,
    ///      both in the tokens' native decimals.
    struct Price {
        uint256 num;
        uint256 denom;
    }

    mapping(address tokenIn => mapping(address tokenOut => Price)) internal _price;

    error PriceNotSet();
    error DeadlinePassed();
    error TooLittleReceived();
    error InsufficientLiquidity();

    event PriceSet(address indexed tokenIn, address indexed tokenOut, uint256 num, uint256 denom);
    event Swapped(
        address indexed payer,
        address indexed recipient,
        address indexed tokenIn,
        address tokenOut,
        uint256 amountIn,
        uint256 amountOut
    );

    constructor(address owner_) Ownable(owner_) { }

    function setPrice(address tokenIn, address tokenOut, uint256 num, uint256 denom)
        external
        onlyOwner
    {
        require(num > 0 && denom > 0, "MockSwapRouter: bad price");
        _price[tokenIn][tokenOut] = Price({ num: num, denom: denom });
        emit PriceSet(tokenIn, tokenOut, num, denom);
    }

    function priceOf(address tokenIn, address tokenOut) external view returns (Price memory) {
        return _price[tokenIn][tokenOut];
    }

    function exactInputSingle(ExactInputSingleParams calldata params)
        external
        returns (uint256 amountOut)
    {
        if (block.timestamp > params.deadline) revert DeadlinePassed();
        Price memory p = _price[params.tokenIn][params.tokenOut];
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
            params.amountIn,
            amountOut
        );
    }
}
