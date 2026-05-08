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
