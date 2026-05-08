// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { IERC20 } from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import { SafeERC20 } from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import { Ownable } from "@openzeppelin/contracts/access/Ownable.sol";

/// @notice Aave-V3-Pool–shape stand-in for testnet fallbacks. Mimics the
///         narrow surface the yield-rotation strategy actually calls:
///         `supply(asset, amount, onBehalfOf, referralCode)`,
///         `withdraw(asset, amount, to)`, and a settable
///         `currentLiquidityRate(asset)`. Per-(supplier, asset) balances
///         accrue at the admin-set APY (basis points, ray-style 1e27 fixed
///         in the on-chain rate read so the SDK can use one decoder for
///         both the real Aave Pool and this mock).
///
///         The contract holds its own inventory of each asset; admin
///         pre-funds before the demo. This contract is the SDK fallback
///         when the real Aave Pool fails the preflight health check —
///         identical call shape, identical accrual semantics.
///
///         phase5-plan.md §WS2.
contract MockYieldVault is Ownable {
    using SafeERC20 for IERC20;

    /// @dev One ray = 1e27, matching Aave V3's ray-fixed rate convention.
    uint256 internal constant RAY = 1e27;
    uint256 internal constant SECONDS_PER_YEAR = 365 days;
    uint256 internal constant BPS = 10_000;

    struct Position {
        uint256 principal; // last-known balance, accrued forward on every touch
        uint256 lastTouch;
    }

    /// @dev Liquidity rate per asset, in ray (1e27). Admin-settable.
    mapping(address asset => uint256 rateRay) public liquidityRateRay;

    mapping(address asset => mapping(address supplier => Position)) internal _positions;

    error AssetNotConfigured(address asset);
    error InsufficientPosition(uint256 requested, uint256 available);

    event LiquidityRateSet(address indexed asset, uint256 rateRay);
    event Supplied(
        address indexed asset, address indexed onBehalfOf, address indexed payer, uint256 amount
    );
    event Withdrawn(
        address indexed asset, address indexed to, address indexed owner, uint256 amount
    );

    constructor(address owner_) Ownable(owner_) { }

    /// @notice Set APY in basis points; converted to a per-second linear
    ///         ray rate matching Aave V3's `currentLiquidityRate` semantics.
    function setApyBps(address asset, uint256 apyBps) external onlyOwner {
        uint256 rateRay = (apyBps * RAY) / BPS;
        liquidityRateRay[asset] = rateRay;
        emit LiquidityRateSet(asset, rateRay);
    }

    /// @notice Direct rate setter for tests that want a non-APY rate (e.g.
    ///         preflight golden values).
    function setLiquidityRateRay(address asset, uint256 rateRay) external onlyOwner {
        liquidityRateRay[asset] = rateRay;
        emit LiquidityRateSet(asset, rateRay);
    }

    /// @notice Mirror of Aave V3 `Pool.getReserveData(asset).currentLiquidityRate`.
    ///         The SDK reads this directly when `venue=MOCK`; the real path
    ///         unpacks the larger ReserveData struct.
    function currentLiquidityRate(address asset) external view returns (uint256) {
        return liquidityRateRay[asset];
    }

    /// @notice Aave-V3 supply shape. `referralCode` is unused — kept for
    ///         calldata parity with the real Pool.
    function supply(
        address asset,
        uint256 amount,
        address onBehalfOf,
        uint16 /*referralCode*/
    )
        external
    {
        if (liquidityRateRay[asset] == 0) revert AssetNotConfigured(asset);
        _accrue(asset, onBehalfOf);
        _positions[asset][onBehalfOf].principal += amount;
        IERC20(asset).safeTransferFrom(msg.sender, address(this), amount);
        emit Supplied(asset, onBehalfOf, msg.sender, amount);
    }

    /// @notice Aave-V3 withdraw shape. Returns the actually-withdrawn
    ///         amount (Aave saturates `amount = type(uint256).max` to the
    ///         full position; we mirror that).
    function withdraw(address asset, uint256 amount, address to) external returns (uint256) {
        _accrue(asset, msg.sender);
        Position storage pos = _positions[asset][msg.sender];
        uint256 toWithdraw = amount == type(uint256).max ? pos.principal : amount;
        if (toWithdraw > pos.principal) {
            revert InsufficientPosition(toWithdraw, pos.principal);
        }
        pos.principal -= toWithdraw;
        IERC20(asset).safeTransfer(to, toWithdraw);
        emit Withdrawn(asset, to, msg.sender, toWithdraw);
        return toWithdraw;
    }

    function balanceOf(address asset, address supplier) external view returns (uint256) {
        Position memory pos = _positions[asset][supplier];
        if (pos.lastTouch == 0) return pos.principal;
        return pos.principal + _accrued(pos, liquidityRateRay[asset]);
    }

    // ── Internals ───────────────────────────────────────────────────

    function _accrue(address asset, address supplier) internal {
        Position storage pos = _positions[asset][supplier];
        if (pos.lastTouch == 0) {
            pos.lastTouch = block.timestamp;
            return;
        }
        uint256 accrued = _accrued(pos, liquidityRateRay[asset]);
        pos.principal += accrued;
        pos.lastTouch = block.timestamp;
    }

    function _accrued(Position memory pos, uint256 rateRay) internal view returns (uint256) {
        if (rateRay == 0 || pos.principal == 0) return 0;
        uint256 elapsed = block.timestamp - pos.lastTouch;
        if (elapsed == 0) return 0;
        // Linear (not compounding) — matches Aave's per-second liquidity rate.
        return (pos.principal * rateRay * elapsed) / (RAY * SECONDS_PER_YEAR);
    }
}
