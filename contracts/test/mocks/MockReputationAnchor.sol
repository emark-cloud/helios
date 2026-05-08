// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { IReputationAnchor } from "../../src/interfaces/IReputationAnchor.sol";

contract MockReputationAnchor is IReputationAnchor {
    address public oApp;

    struct LastCall {
        address actor;
        ActorType actorType;
        int256 score;
        bool seen;
    }

    LastCall public lastCall;
    uint256 public callCount;
    /// @dev Per-actor counter incremented by postCrossChainTradeTick. Lets
    ///      tests assert the H3/H4 fix routes batches through the
    ///      tick-only entrypoint instead of clobbering score via
    ///      postCrossChainUpdate.
    mapping(address => uint256) public trackedTradeTicks;
    uint256 public tickCallCount;
    address public lastTickActor;

    function setOApp(address oApp_) external {
        oApp = oApp_;
    }

    function postCrossChainUpdate(address actor, ActorType actorType, ReputationData calldata data)
        external
    {
        require(msg.sender == oApp, "not-oapp");
        lastCall =
            LastCall({ actor: actor, actorType: actorType, score: data.currentScore, seen: true });
        callCount += 1;
        emit CrossChainReputationPosted(actor, actorType, 0, data.currentScore);
    }

    function postCrossChainTradeTick(address actor) external {
        require(msg.sender == oApp, "not-oapp");
        unchecked {
            trackedTradeTicks[actor] += 1;
        }
        tickCallCount += 1;
        lastTickActor = actor;
        emit CrossChainTradeTick(actor, trackedTradeTicks[actor]);
    }

    function postReputationUpdate(address, ActorType, ReputationData calldata, bytes calldata)
        external
        pure
    {
        revert("unused");
    }

    function reputationOf(address) external pure returns (ReputationData memory) {
        revert("unused");
    }
}
