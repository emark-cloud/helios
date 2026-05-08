// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { DeployPhase5Execution } from "./DeployPhase5Execution.s.sol";

/// @notice Phase-5 entry point — `forge script DeployBaseSepolia` deploys
///         the Helios execution-chain surface to Base Sepolia. Inherits
///         all behavior from `DeployPhase5Execution`; the chain-specific
///         venue (canonical Uniswap V3 + MockUniswapV3Router fallback) is
///         selected by `block.chainid == 84_532` inside the parent.
contract DeployBaseSepolia is DeployPhase5Execution { }
