// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { OFTAdapter } from "@layerzerolabs/oapp-evm/oft/OFTAdapter.sol";
import { Ownable } from "@openzeppelin/contracts/access/Ownable.sol";

/// @title MUsdcOFTAdapter
/// @notice CXR-0a — LayerZero V2 OFT adapter wrapping the existing mUSDC
///         (MockERC20) deployed on Kite testnet, Arbitrum-Sepolia, and
///         Base-Sepolia. Deploys identically on each chain; LZ peers are
///         wired bidirectionally via `WireOFTPeers.s.sol`.
///
///         Default lock-and-release semantics. Each chain's adapter
///         carries an inventory of mUSDC equal to the maximum imbalance
///         it ever needs to release. Pre-funded by the deployer at
///         broadcast time (100k mUSDC per chain — sufficient for v1
///         demo throughput).
///
///         Composable: `OFTCore.send` accepts a `composeMsg` payload
///         that the receiver decodes via
///         `HeliosBridgeReceiver.lzCompose`. That payload carries the
///         destination strategy id + remote vault address so the
///         bridge releases mUSDC and atomically credits the local
///         StrategyVault via `onCrossChainAllocate`.
contract MUsdcOFTAdapter is OFTAdapter {
    constructor(address mUsdc_, address lzEndpoint_, address delegate_)
        OFTAdapter(mUsdc_, lzEndpoint_, delegate_)
        Ownable(delegate_)
    { }
}
