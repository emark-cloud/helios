// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {
    MessagingParams,
    MessagingFee,
    MessagingReceipt,
    Origin
} from "@layerzerolabs/lz-evm-protocol-v2/contracts/interfaces/ILayerZeroEndpointV2.sol";

interface IOAppLzReceive {
    function lzReceive(
        Origin calldata origin,
        bytes32 guid,
        bytes calldata message,
        address executor,
        bytes calldata extraData
    ) external payable;
}

/// @notice Minimum LayerZero endpoint shim used only by Foundry tests for
///         HeliosOApp. Exposes the four functions OApp actually calls
///         (setDelegate, quote, send, lzToken) plus a `deliver` helper that
///         lets the test drive an inbound message synchronously.
///
///         Pairs with a sibling MockLzEndpoint to simulate two chains: each
///         endpoint knows its own EID and a single peer endpoint address.
///         Cast as ILayerZeroEndpointV2 inside OApp via address typecast —
///         we do not implement the full interface to keep this mock small.
contract MockLzEndpoint {
    uint32 public immutable eid;
    MockLzEndpoint public peer;

    address public delegate;
    uint64 public outboundNonce;
    uint64 public inboundNonce;

    uint256 public nativeFee;
    uint256 public lzTokenFeeAmount;
    address public lzTokenAddr;

    bytes public lastMessage;
    bytes public lastOptions;
    address public lastReceiver;

    constructor(uint32 eid_) {
        eid = eid_;
    }

    function setPeer(MockLzEndpoint peer_) external {
        peer = peer_;
    }

    function setFee(uint256 native_, uint256 lzTokenFee_, address lzToken_) external {
        nativeFee = native_;
        lzTokenFeeAmount = lzTokenFee_;
        lzTokenAddr = lzToken_;
    }

    // ── Calls OApp makes ────────────────────────────────────────────

    function setDelegate(address delegate_) external {
        delegate = delegate_;
    }

    function lzToken() external view returns (address) {
        return lzTokenAddr;
    }

    function quote(MessagingParams calldata, address) external view returns (MessagingFee memory) {
        return MessagingFee({ nativeFee: nativeFee, lzTokenFee: lzTokenFeeAmount });
    }

    function send(
        MessagingParams calldata p,
        address /*refundAddress*/
    )
        external
        payable
        returns (MessagingReceipt memory receipt)
    {
        outboundNonce += 1;
        bytes32 guid = keccak256(abi.encodePacked(eid, p.dstEid, outboundNonce, p.message));
        lastMessage = p.message;
        lastOptions = p.options;
        lastReceiver = address(uint160(uint256(p.receiver)));

        receipt = MessagingReceipt({
            guid: guid,
            nonce: outboundNonce,
            fee: MessagingFee({ nativeFee: msg.value, lzTokenFee: 0 })
        });
    }

    // ── Test driver: deliver `lastMessage` to peer ──────────────────

    /// @notice Pretend the LZ DVN/executor verified our last sent packet and
    ///         deliver it on the peer endpoint. Test must call on the source
    ///         endpoint and pass the destination OApp address.
    function deliverTo(address dstOApp, bytes32 srcOAppPeer) external returns (bytes32 guid) {
        require(address(peer) != address(0), "peer-not-set");
        peer.inboundDeliver(eid, srcOAppPeer, dstOApp, lastMessage);
        guid = keccak256(abi.encodePacked(eid, peer.eid(), outboundNonce, lastMessage));
    }

    function inboundDeliver(uint32 srcEid, bytes32 sender, address dstOApp, bytes calldata message)
        external
    {
        inboundNonce += 1;
        bytes32 guid = keccak256(abi.encodePacked(srcEid, eid, inboundNonce, message));
        Origin memory origin = Origin({ srcEid: srcEid, sender: sender, nonce: inboundNonce });
        IOAppLzReceive(dstOApp).lzReceive(origin, guid, message, address(this), "");
    }
}
