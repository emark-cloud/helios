// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { IReputationAnchor } from "./IReputationAnchor.sol";

/// @notice LayerZero OApp for cross-chain reputation + capital bridging hooks.
///         Kite is canonical; Base/Arbitrum are execution venues.
///         Helios.md §6.9, §12.
interface IHeliosOApp {
    struct MessagingFee {
        uint256 nativeFee;
        uint256 lzTokenFee;
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

    function sendReputationUpdate(
        uint32 dstEid,
        address actor,
        IReputationAnchor.ActorType actorType,
        IReputationAnchor.ReputationData calldata data,
        bytes calldata options
    ) external payable;

    function quote(uint32 dstEid, bytes calldata payload, bytes calldata options)
        external
        view
        returns (MessagingFee memory);
}
