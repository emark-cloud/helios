// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";
import { HeliosOApp } from "../src/HeliosOApp.sol";
import { IHeliosOApp } from "../src/interfaces/IHeliosOApp.sol";
import { IReputationAnchor } from "../src/interfaces/IReputationAnchor.sol";
import { CrossChainCodec } from "../src/lib/CrossChainCodec.sol";

/// @notice WS10.6 — bare-metal cross-chain reputation send. Allowlists the
///         deployer EOA as a "strategy vault" on the source OApp, builds a
///         minimal ReputationData payload, quotes the LZ V2 fee, and ships
///         the message to Kite. Emits ReputationMessageSent on source; pair
///         with ReputationMessageReceived on Kite via the GUID returned.
///
///         Required env:
///           - DEPLOYER_PK
///           - SRC_OAPP   (HeliosOApp on the source chain)
///           - DST_EID    (destination EID, e.g. 40415 for Kite)
contract TriggerXChainSend is Script {
    function run() external {
        uint256 pk = vm.envUint("DEPLOYER_PK");
        address deployer = vm.addr(pk);
        address srcOAppAddr = vm.envAddress("SRC_OAPP");
        uint32 dstEid = uint32(vm.envUint("DST_EID"));

        HeliosOApp oapp = HeliosOApp(srcOAppAddr);

        IReputationAnchor.ReputationData memory data = IReputationAnchor.ReputationData({
            currentScore: 750,
            lastUpdateBlock: block.number,
            totalAttestedTrades: 1,
            totalRealizedPnL: 0,
            maxDrawdownBps: 100,
            proofValidityRateBps: 10_000,
            actorType: IReputationAnchor.ActorType.STRATEGY,
            componentsHash: bytes32(uint256(0xDEAD))
        });

        // Build the same payload the contract will build, so we can quote.
        uint64 nextSeq = oapp.lastSeqOut(deployer) + 1;
        bytes memory payload = CrossChainCodec.encodeReputationUpdate(
            CrossChainCodec.ReputationUpdateV1({
                seq: nextSeq,
                actor: deployer,
                actorType: IReputationAnchor.ActorType.STRATEGY,
                data: data
            })
        );

        // Default LZ V2 options: empty bytes is valid but uses zero executor
        // gas. Use the type-3 worker-options-builder format: 0x0003 + gas option.
        // OptionsBuilder.newOptions() returns 0x0003; we manually compose
        // addExecutorLzReceiveOption(gas, value=0).
        // Type 1 option layout: workerId(1) | optionType(2) | optionPayload.
        // executor opt-type-3 (LzReceiveOption) payload = abi.encode(gas, 0).
        bytes memory options = abi.encodePacked(
            uint16(3), // OPTIONS_TYPE_3
            uint8(1), // worker_id = executor
            uint16(17), // option_size = 1 (option_type) + 16 (gas) = 17
            uint8(1), // OPTION_TYPE_LZRECEIVE
            uint128(200_000) // gas
        );

        IHeliosOApp.MessagingFee memory fee = oapp.quote(dstEid, payload, options);
        console2.log("== Quote ==");
        console2.log("  dstEid:    ", dstEid);
        console2.log("  payload (bytes):", payload.length);
        console2.log("  nativeFee: ", fee.nativeFee);

        vm.startBroadcast(pk);
        // Allowlist self as a strategy-vault caller (idempotent).
        oapp.setStrategyVault(deployer, true);
        // Pay 20% slack on the quoted fee.
        uint256 sendValue = fee.nativeFee + (fee.nativeFee / 5);
        oapp.sendReputationUpdate{ value: sendValue }(
            dstEid, deployer, IReputationAnchor.ActorType.STRATEGY, data, options
        );
        vm.stopBroadcast();

        console2.log("send broadcast (value=", sendValue, "wei)");
        console2.log("watch dst chain for ReputationMessageReceived w/ matching guid");
    }
}
