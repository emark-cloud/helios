// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { ERC20 } from "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/// @notice MockERC20 variant with constructor-set decimals.
///         Used by Phase-6 multi-asset universe (mWBTC=8, mWETH=18, mSOL=9)
///         so on-chain decimals match real-world expectations and the
///         oracle->router price keeper can normalize correctly.
///         The default `MockERC20` (decimals=18) stays the canonical mUSDC
///         shape; this contract is only for the new universe assets.
contract MockTestToken is ERC20 {
    uint8 private immutable _decimals;

    constructor(string memory n, string memory s, uint8 d) ERC20(n, s) {
        _decimals = d;
    }

    function decimals() public view virtual override returns (uint8) {
        return _decimals;
    }

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}
