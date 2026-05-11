// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";
import { HeliosOApp } from "../src/HeliosOApp.sol";
import { IHeliosOApp } from "../src/interfaces/IHeliosOApp.sol";
import { IReputationAnchor } from "../src/interfaces/IReputationAnchor.sol";
import { CrossChainCodec } from "../src/lib/CrossChainCodec.sol";

/// @notice WS10.6/7 — bare-metal cross-chain BATCH send. Unlike
///         `sendReputationUpdate` (which calls `postCrossChainUpdate` →
///         `StrategyRegistry.updateReputation`, gated on the actor being a
///         registered strategy), the batch path lands as
///         `postCrossChainTradeTick` on the canonical anchor — a
///         counter-only increment that doesn't touch the registry. Suitable
///         for **infrastructure** verification: proves the LZ V2 wiring,
///         peer trust, DVN delivery, and `_lzReceive` decoder all work
///         without requiring registered-strategy chain state.
///
///         Required env:
///           - DEPLOYER_PK
///           - SRC_OAPP   (HeliosOApp on the source chain)
///           - DST_EID    (destination EID, e.g. 40415 for Kite)
contract TriggerXChainBatch is Script {
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
            componentsHash: bytes32(uint256(0xCAFE))
        });

        // Pre-compute the batch payload locally to drive the quote.
        uint64 nextSeq = oapp.lastSeqOut(deployer) + 1;
        CrossChainCodec.ReputationBatchEntry[] memory batch =
            new CrossChainCodec.ReputationBatchEntry[](1);
        batch[0] =
            CrossChainCodec.ReputationBatchEntry({ seq: nextSeq, strategy: deployer, data: data });
        bytes memory payload = CrossChainCodec.encodeReputationBatch(batch);

        bytes memory options =
            abi.encodePacked(uint16(3), uint8(1), uint16(17), uint8(1), uint128(250_000));

        IHeliosOApp.MessagingFee memory fee = oapp.quote(dstEid, payload, options);
        console2.log("== batch quote ==");
        console2.log("  dstEid:    ", dstEid);
        console2.log("  payload:   ", payload.length, "bytes");
        console2.log("  nativeFee: ", fee.nativeFee);

        vm.startBroadcast(pk);
        // Self-allowlist (idempotent if already done by WS10.6).
        oapp.setStrategyVault(deployer, true);
        // Queue one entry under our own strategy address (= deployer).
        oapp.queueAttestation(deployer, data);
        // Flush with 20% slack on the fee.
        uint256 sendValue = fee.nativeFee + (fee.nativeFee / 5);
        bytes32 guid = oapp.flushAttestationsFor{ value: sendValue }(deployer, dstEid, options);
        vm.stopBroadcast();

        console2.log("flush guid:");
        console2.logBytes32(guid);
    }
}
