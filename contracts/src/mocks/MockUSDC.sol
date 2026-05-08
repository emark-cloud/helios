// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { OFT } from "@layerzerolabs/oapp-evm/oft/OFT.sol";
import { Ownable } from "@openzeppelin/contracts/access/Ownable.sol";

/// @notice Cross-chain demo USDC built on LayerZero V2 OFT. Owner can mint
///         on Kite for the demo capital float; OFT.send burns on the source
///         chain and mints on the destination via the standard OFT path.
///         Real USDC on testnets is fragmented across faucets and not
///         OFT-wrapped, so we use this token to keep the bridge
///         deterministic. Trade execution still hits the real Uniswap V3 /
///         Aave V3 pools on the destination chain.
///
///         phase5-plan.md §WS2.
contract MockUSDC is OFT {
    constructor(address lzEndpoint, address delegate)
        OFT("Helios Mock USDC", "mUSDC", lzEndpoint, delegate)
        Ownable(delegate)
    { }

    /// @notice 6 decimals — matches real USDC for SDK arithmetic.
    function decimals() public pure override returns (uint8) {
        return 6;
    }

    /// @notice Owner-only mint for seeding demo capital on the canonical chain.
    function mint(address to, uint256 amount) external onlyOwner {
        _mint(to, amount);
    }
}
