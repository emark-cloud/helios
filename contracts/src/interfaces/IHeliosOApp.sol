// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { IReputationAnchor } from "./IReputationAnchor.sol";

/// @notice LayerZero OApp for cross-chain reputation + capital bridging hooks.
///         Kite is canonical; Base/Arbitrum are execution venues.
///         Helios.md §6.9, §12; phase5-plan.md §WS1.
interface IHeliosOApp {
    struct MessagingFee {
        uint256 nativeFee;
        uint256 lzTokenFee;
    }

    /// @notice One pending attestation slot, queued on a non-canonical chain
    ///         pending the next flush to Kite.
    struct PendingAttestation {
        address strategy;
        IReputationAnchor.ReputationData data;
    }

    event ReputationMessageSent(
        uint32 indexed dstEid,
        address indexed actor,
        IReputationAnchor.ActorType actorType,
        bytes32 guid
    );
    event ReputationMessageReceived(
        uint32 indexed srcEid,
        address indexed actor,
        IReputationAnchor.ActorType actorType,
        bytes32 guid
    );
    event AttestationQueued(address indexed strategy, uint64 indexed seq, uint256 queueLength);
    event AttestationsFlushed(
        uint32 indexed dstEid, uint256 batchSize, uint64 firstSeq, uint64 lastSeq, bytes32 guid
    );
    event BridgeAndDeploySent(
        uint32 indexed dstEid, address indexed strategy, uint256 amount, bytes32 guid
    );
    event BridgeAndDeployReceived(
        uint32 indexed srcEid, address indexed strategy, uint256 amount, bytes32 guid
    );

    error PeerNotSet(uint32 dstEid);
    error ReplaySeq(uint32 srcEid, address actor, uint64 seq, uint64 lastSeq);
    error QueueFull(address strategy, uint256 cap);
    error EmptyQueue(address strategy);
    error NotStrategyVault(address caller);
    error UnknownPayloadKind(uint8 kind);
    error CrossChainOnly(uint64 chainId);
    /// @dev `sendReputationUpdate` requires `actor == msg.sender` so a vault
    ///      can only attest its own reputation. `bridgeAndDeploy` likewise
    ///      requires `strategyOnDst == msg.sender` so a vault can only credit
    ///      capital to itself on the destination chain.
    error CallerActorMismatch(address caller, address actor);

    /// @notice Send a single reputation update from a non-canonical chain to Kite.
    ///         Used for the “strategy executes locally → reputation ticks on Kite” path
    ///         when the local engine wants to commit immediately rather than batch.
    function sendReputationUpdate(
        uint32 dstEid,
        address actor,
        IReputationAnchor.ActorType actorType,
        IReputationAnchor.ReputationData calldata data,
        bytes calldata options
    ) external payable;

    /// @notice Strategy vaults call this after a successful executeWithProof on a
    ///         non-canonical chain. The OApp accumulates pending attestations until
    ///         flushAttestations is called.
    function queueAttestation(address strategy, IReputationAnchor.ReputationData calldata data)
        external;

    /// @notice Pack a strategy’s pending attestation queue into a single
    ///         REPUTATION_UPDATE_V1 batch payload and ship it to dstEid
    ///         (always Kite in v1). Returns the LayerZero guid for tracking.
    function flushAttestationsFor(address strategy, uint32 dstEid, bytes calldata options)
        external
        payable
        returns (bytes32 guid);

    /// @notice Demo capital path: bridges mock USDC to a strategy on dstEid and
    ///         signals the destination StrategyVault to credit the deposit.
    ///         Pairs with an OFT.send on the source side.
    function bridgeAndDeploy(
        uint32 dstEid,
        address strategyOnDst,
        uint256 amount,
        bytes calldata options
    ) external payable;

    function quote(uint32 dstEid, bytes calldata payload, bytes calldata options)
        external
        view
        returns (MessagingFee memory);

    function pendingCount(address strategy) external view returns (uint256);
    function lastSeqIn(uint32 srcEid, address actor) external view returns (uint64);
    function lastSeqOut(address strategy) external view returns (uint64);
    function maxPendingPerStrategy() external view returns (uint256);
}
