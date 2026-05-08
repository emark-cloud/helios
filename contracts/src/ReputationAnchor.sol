// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Ownable } from "@openzeppelin/contracts/access/Ownable.sol";
import { Pausable } from "@openzeppelin/contracts/utils/Pausable.sol";
import { EIP712 } from "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import { ECDSA } from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";

import { IReputationAnchor } from "./interfaces/IReputationAnchor.sol";
import { IStrategyRegistry } from "./interfaces/IStrategyRegistry.sol";
import { IAllocatorRegistry } from "./interfaces/IAllocatorRegistry.sol";

/// @title ReputationAnchor
/// @notice Canonical reputation source for both strategies and allocators.
///         Off-chain Reputation Engine signs updates with the registered
///         signer key; this contract verifies, stores, and pushes the delta
///         into the appropriate registry. Cross-chain updates flow through
///         the LayerZero OApp.  Helios.md §6.8.
contract ReputationAnchor is IReputationAnchor, Ownable, Pausable, EIP712 {
    bytes32 private constant _UPDATE_TYPEHASH = keccak256(
        "ReputationUpdate(address actor,uint8 actorType,int256 currentScore,uint256 lastUpdateBlock,uint256 totalAttestedTrades,uint256 totalRealizedPnL,uint256 maxDrawdownBps,uint256 proofValidityRateBps)"
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

    error ZeroAddress();
    error RegistriesAlreadySet();
    error StaleUpdate();
    error UnknownActorType();

    constructor(address signer_, address oApp_, address owner_)
        Ownable(owner_)
        EIP712("HeliosReputationAnchor", "1")
    {
        if (signer_ == address(0)) revert ZeroAddress();
        // oApp may be the zero address at construction — Phase 5 wires the
        // real LayerZero endpoint; until then cross-chain calls are gated by
        // the existing onlyOApp check (which will reject zero by accident).
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

    /// @notice Owner-only emergency stop. Halts both off-chain and
    ///         cross-chain reputation updates so a compromised signer or
    ///         OApp can't continue posting while remediation is underway.
    ///         Phase-3 review MEDIUM in `docs/phase-3-review.md`.
    function pause() external onlyOwner {
        _pause();
    }

    function unpause() external onlyOwner {
        _unpause();
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
    ) external whenNotPaused {
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
                data.proofValidityRateBps
            )
        );
        bytes32 digest = _hashTypedDataV4(structHash);
        address recovered = ECDSA.recover(digest, signerSignature);
        if (recovered != reputationSigner) revert InvalidSigner();

        _applyUpdate(actor, actorType, data);
        lastUpdateBySource[reputationSigner] = uint64(block.timestamp);

        emit ReputationPosted(actor, actorType, data.currentScore, block.number);
    }

    // ── Cross-chain update (OApp gated) ─────────────────────────────

    function postCrossChainUpdate(address actor, ActorType actorType, ReputationData calldata data)
        external
        whenNotPaused
    {
        if (msg.sender != oApp) revert NotOApp();
        _applyUpdate(actor, actorType, data);
        lastUpdateBySource[oApp] = uint64(block.timestamp);

        emit CrossChainReputationPosted(actor, actorType, 0, data.currentScore);
    }

    /// @notice Counter-only cross-chain tick. Increments
    ///         `totalAttestedTrades` for `actor` and emits a tick event;
    ///         leaves `currentScore`, `totalRealizedPnL`, `maxDrawdownBps`,
    ///         `proofValidityRateBps`, and `lastUpdateBlock` untouched. The
    ///         off-chain engine remains the authoritative source of scores;
    ///         no registry delta is propagated.
    ///
    ///         Phase-5 review H3 (avoid score-zeroing on remote trades) and
    ///         H4 (avoid `lastUpdateBlock` collisions across chain block
    ///         numbers that would freeze the engine via StaleUpdate).
    function postCrossChainTradeTick(address actor) external whenNotPaused {
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
                data.proofValidityRateBps
            )
        );
        return _hashTypedDataV4(structHash);
    }

    // ── Internal ────────────────────────────────────────────────────

    function _applyUpdate(address actor, ActorType actorType, ReputationData calldata data)
        internal
    {
        ReputationData storage prev = _reputations[actor];
        // Replay protection via monotonic block. The first update for an
        // actor passes (prev.lastUpdateBlock == 0); subsequent updates must
        // strictly advance.
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
