// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

/// @notice Shared meta-strategy record signed once by the user.
///         See Helios.md §6.2 and §6.3 (auto-defund TWAP/bond/confirm window).
library MetaStrategyLib {
    /// @dev Default auto-defund knobs. Applied by UserVault when the caller
    ///      submits zeros so older payloads round-trip without surprise. The
    ///      enforcement path lands in Phase 4 (`AllocatorVault.defundStrategy`).
    uint16 internal constant DEFAULT_DEFUND_TWAP_BARS = 3;
    uint16 internal constant DEFAULT_DEFUND_BOND_BPS = 50;
    uint32 internal constant DEFAULT_DEFUND_CONFIRM_BLOCKS = 25;

    struct MetaStrategy {
        bytes32 metaStrategyHash; // Poseidon hash of the canonical payload
        bytes32[] allowedStrategyClasses;
        address[] allowedAssets;
        uint32[] allowedChains; // chain ids
        uint256 maxCapital;
        uint16 maxPerStrategyBps; // e.g., 3_000 = 30%
        uint8 maxStrategiesCount;
        uint16 drawdownThresholdBps; // e.g., 1_500 = 15%
        uint16 maxFeeRateBps; // e.g., 2_500 = 25%
        uint256 rebalanceCadenceSec;
        uint64 validUntil;
        // WS7.C — auto-defund griefing controls. Phase 2 stores them; Phase 4
        // wires the AllocatorVault TWAP/bond/confirm enforcement.
        uint16 defundTwapBars; // consecutive 5-min OraclePriceAnchor snapshots a breach must persist
        uint16 defundBondBps; // forfeit bond size (bps of the position) the trigger caller posts
        uint32 defundConfirmBlocks; // confirmation window before the trigger executes
    }
}
