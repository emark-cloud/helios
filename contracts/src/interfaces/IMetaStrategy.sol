// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

/// @notice Shared meta-strategy record signed once by the user.
///         See Helios.md §6.2.
library MetaStrategyLib {
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
    }
}
