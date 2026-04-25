// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

/// @notice Reputation anchor for both strategies and allocators, distinguished by actorType.
///         Receives off-chain engine updates and cross-chain LayerZero updates.
///         Helios.md §6.8.
interface IReputationAnchor {
    enum ActorType {
        STRATEGY,
        ALLOCATOR
    }

    struct ReputationData {
        int256 currentScore;             // e.g., [-10_000, +10_000]
        uint256 lastUpdateBlock;
        uint256 totalAttestedTrades;    // strategies: trades; allocators: rebalance ops
        uint256 totalRealizedPnL;       // strategies: own P&L; allocators: aggregate user P&L
        uint256 maxDrawdownBps;
        uint256 proofValidityRateBps;   // strategies only; always 10_000 for allocators
        ActorType actorType;
    }

    event ReputationPosted(
        address indexed actor,
        ActorType indexed actorType,
        int256 newScore,
        uint256 blockNumber
    );
    event CrossChainReputationPosted(
        address indexed actor,
        ActorType indexed actorType,
        uint32 srcEid,
        int256 newScore
    );

    error InvalidSigner();
    error NotOApp();

    function postReputationUpdate(
        address actor,
        ActorType actorType,
        ReputationData calldata data,
        bytes calldata signerSignature
    ) external;

    function postCrossChainUpdate(
        address actor,
        ActorType actorType,
        ReputationData calldata data
    ) external;

    function reputationOf(address actor) external view returns (ReputationData memory);
}
