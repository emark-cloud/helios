// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { DeployPhase5Execution } from "./DeployPhase5Execution.s.sol";

/// @notice Phase-5 entry point — `forge script DeployArbitrumSepolia`
///         deploys the Helios execution-chain surface to Arbitrum Sepolia.
///         Inherits all behavior from `DeployPhase5Execution`; the
///         chain-specific venue (canonical Aave V3 + MockYieldVault
///         fallback) is selected by `block.chainid == 421_614` inside the
///         parent.
contract DeployArbitrumSepolia is DeployPhase5Execution { }
