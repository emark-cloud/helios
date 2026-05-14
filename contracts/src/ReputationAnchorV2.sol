// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Ownable } from "@openzeppelin/contracts/access/Ownable.sol";
import { EIP712 } from "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import { ECDSA } from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";

import { IReputationAnchor } from "./interfaces/IReputationAnchor.sol";
import { IStrategyRegistry } from "./interfaces/IStrategyRegistry.sol";
import { IAllocatorRegistry } from "./interfaces/IAllocatorRegistry.sol";

/// @title ReputationAnchorV2
/// @notice Phase-2 reputation anchor. Mirrors V1 but binds the engine's
///         §8.2 component vector into the EIP-712 typehash via
///         `componentsHash`, so the audit page can re-verify the score
///         breakdown the engine claimed it used. Domain version is bumped
///         to "2" — V1 signatures will not validate against this contract.
///
///         Deployed fresh (V1 was non-upgradeable). Both anchors can run
///         side-by-side during the cutover; subgraph follows V2 going
///         forward.
///
///         CUTOVER NOTE — v1↔v2: Phase-1 registries were constructed with
///         `reputationAnchor = ReputationAnchorV1` (immutable in
///         StrategyRegistry/AllocatorRegistry). If `setRegistries` here
///         is wired to a V1-bound registry, the very first
///         `postReputationUpdate` reverts with `NotReputationAnchor`
///         from the registry (V2 is not a trusted caller). Phase-2
///         intentionally does NOT call `setRegistries` — V2 acts as a
///         sidecar publisher (stores `ReputationData` + emits
///         `ReputationPosted`/`ComponentsAnchored`) and leaves the
///         registries' on-chain `currentReputation` last-touched by V1.
///         The full v1→v2 cutover (registry redeploy) lands in Phase 5.
contract ReputationAnchorV2 is IReputationAnchor, Ownable, EIP712 {
    bytes32 private constant _UPDATE_TYPEHASH = keccak256(
        "ReputationUpdate(address actor,uint8 actorType,int256 currentScore,uint256 lastUpdateBlock,uint256 totalAttestedTrades,uint256 totalRealizedPnL,uint256 maxDrawdownBps,uint256 proofValidityRateBps,bytes32 componentsHash)"
    );

    address public reputationSigner;
    address public oApp;
    IStrategyRegistry public strategyRegistry;
    IAllocatorRegistry public allocatorRegistry;

    mapping(address => ReputationData) internal _reputations;
    mapping(address => uint64) public lastUpdateBySource;

    event SignerUpdated(address indexed previous, address indexed next);
    event OAppUpdated(address indexed previous, address indexed next);
    event RegistriesSet(address strategyRegistry, address allocatorRegistry);
    event ComponentsAnchored(address indexed actor, bytes32 componentsHash);

    error ZeroAddress();
    error RegistriesAlreadySet();
    error StaleUpdate();
    error UnknownActorType();

    constructor(address signer_, address oApp_, address owner_)
        Ownable(owner_)
        EIP712("HeliosReputationAnchor", "2")
    {
        if (signer_ == address(0)) revert ZeroAddress();
        reputationSigner = signer_;
        oApp = oApp_;
    }

    // ── One-time registry wiring ────────────────────────────────────

    function setRegistries(address strategyRegistry_, address allocatorRegistry_)
        external
        onlyOwner
    {
        if (address(strategyRegistry) != address(0)) revert RegistriesAlreadySet();
        if (strategyRegistry_ == address(0) || allocatorRegistry_ == address(0)) {
            revert ZeroAddress();
        }
        strategyRegistry = IStrategyRegistry(strategyRegistry_);
        allocatorRegistry = IAllocatorRegistry(allocatorRegistry_);
        emit RegistriesSet(strategyRegistry_, allocatorRegistry_);
    }

    function setSigner(address signer_) external onlyOwner {
        if (signer_ == address(0)) revert ZeroAddress();
        emit SignerUpdated(reputationSigner, signer_);
        reputationSigner = signer_;
    }

    function setOApp(address oApp_) external onlyOwner {
        emit OAppUpdated(oApp, oApp_);
        oApp = oApp_;
    }

    // ── Off-chain engine update ─────────────────────────────────────

    function postReputationUpdate(
        address actor,
        ActorType actorType,
        ReputationData calldata data,
        bytes calldata signerSignature
    ) external {
        bytes32 structHash = keccak256(
            abi.encode(
                _UPDATE_TYPEHASH,
                actor,
                uint8(actorType),
                data.currentScore,
                data.lastUpdateBlock,
                data.totalAttestedTrades,
                data.totalRealizedPnL,
                data.maxDrawdownBps,
                data.proofValidityRateBps,
                data.componentsHash
            )
        );
        bytes32 digest = _hashTypedDataV4(structHash);
        address recovered = ECDSA.recover(digest, signerSignature);
        if (recovered != reputationSigner) revert InvalidSigner();

        _applyUpdate(actor, actorType, data);
        lastUpdateBySource[reputationSigner] = uint64(block.timestamp);

        emit ReputationPosted(actor, actorType, data.currentScore, block.number);
        emit ComponentsAnchored(actor, data.componentsHash);
    }

    // ── Cross-chain update (OApp gated) ─────────────────────────────

    function postCrossChainUpdate(address actor, ActorType actorType, ReputationData calldata data)
        external
    {
        if (msg.sender != oApp) revert NotOApp();
        _applyUpdate(actor, actorType, data);
        lastUpdateBySource[oApp] = uint64(block.timestamp);

        emit CrossChainReputationPosted(actor, actorType, 0, data.currentScore);
        emit ComponentsAnchored(actor, data.componentsHash);
    }

    /// @notice Counter-only cross-chain tick mirroring ReputationAnchor V1.
    ///         Increments `totalAttestedTrades`; leaves all engine-managed
    ///         fields and `lastUpdateBlock` untouched. Phase-5 review H3, H4.
    function postCrossChainTradeTick(address actor) external {
        if (msg.sender != oApp) revert NotOApp();
        ReputationData storage rep = _reputations[actor];
        unchecked {
            rep.totalAttestedTrades += 1;
        }
        lastUpdateBySource[oApp] = uint64(block.timestamp);
        emit CrossChainTradeTick(actor, rep.totalAttestedTrades);
    }

    // ── Views ───────────────────────────────────────────────────────

    function reputationOf(address actor) external view returns (ReputationData memory) {
        return _reputations[actor];
    }

    function domainSeparator() external view returns (bytes32) {
        return _domainSeparatorV4();
    }

    function hashUpdate(address actor, ActorType actorType, ReputationData calldata data)
        external
        view
        returns (bytes32)
    {
        bytes32 structHash = keccak256(
            abi.encode(
                _UPDATE_TYPEHASH,
                actor,
                uint8(actorType),
                data.currentScore,
                data.lastUpdateBlock,
                data.totalAttestedTrades,
                data.totalRealizedPnL,
                data.maxDrawdownBps,
                data.proofValidityRateBps,
                data.componentsHash
            )
        );
        return _hashTypedDataV4(structHash);
    }

    // ── Internal ────────────────────────────────────────────────────

    function _applyUpdate(address actor, ActorType actorType, ReputationData calldata data)
        internal
    {
        ReputationData storage prev = _reputations[actor];
        if (prev.lastUpdateBlock != 0 && data.lastUpdateBlock <= prev.lastUpdateBlock) {
            revert StaleUpdate();
        }

        int256 delta = data.currentScore - prev.currentScore;
        _reputations[actor] = data;

        if (actorType == ActorType.STRATEGY) {
            if (address(strategyRegistry) != address(0)) {
                strategyRegistry.updateReputation(actor, delta);
            }
        } else if (actorType == ActorType.ALLOCATOR) {
            if (address(allocatorRegistry) != address(0)) {
                allocatorRegistry.updateReputation(actor, delta);
            }
        } else {
            revert UnknownActorType();
        }
    }
}
