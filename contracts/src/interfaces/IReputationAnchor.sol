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
        int256 currentScore; // e.g., [-10_000, +10_000]
        uint256 lastUpdateBlock;
        uint256 totalAttestedTrades; // strategies: trades; allocators: rebalance ops
        uint256 totalRealizedPnL; // strategies: own P&L; allocators: aggregate user P&L
        uint256 maxDrawdownBps;
        uint256 proofValidityRateBps; // strategies only; always 10_000 for allocators
        ActorType actorType;
        // V2: keccak256-encoded fingerprint of the §8.2 component vector
        // (R_pnl, R_drawdown, R_consistency, R_proof, R_age) the engine used
        // to compute currentScore. Anchored on chain so audit consumers can
        // re-verify the score breakdown without trusting the engine response.
        bytes32 componentsHash;
    }

    event ReputationPosted(
        address indexed actor, ActorType indexed actorType, int256 newScore, uint256 blockNumber
    );
    event CrossChainReputationPosted(
        address indexed actor, ActorType indexed actorType, uint32 srcEid, int256 newScore
    );
    /// @notice Counter-only ping from a cross-chain attestation flush.
    ///         Increments `totalAttestedTrades` for the actor without
    ///         touching the engine-authoritative score / PnL / drawdown
    ///         fields. Phase-5 review H3, H4.
    event CrossChainTradeTick(
        address indexed actor, uint256 newTotalAttestedTrades
    );

    error InvalidSigner();
    error NotOApp();

    function postReputationUpdate(
        address actor,
        ActorType actorType,
        ReputationData calldata data,
        bytes calldata signerSignature
    ) external;

    function postCrossChainUpdate(address actor, ActorType actorType, ReputationData calldata data)
        external;

    /// @notice OApp-gated counter increment. Used by the cross-chain
    ///         attestation forwarder so a successful trade on Base/Arb bumps
    ///         `totalAttestedTrades` on the canonical anchor without
    ///         clobbering the score/PnL/lastUpdateBlock that the off-chain
    ///         engine maintains. Phase-5 review H3, H4.
    function postCrossChainTradeTick(address actor) external;

    function reputationOf(address actor) external view returns (ReputationData memory);
}
