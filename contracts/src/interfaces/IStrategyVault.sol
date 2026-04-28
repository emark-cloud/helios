// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

/// @notice StrategyVault — per-strategy capital + ZK-gated trade execution + NAV tracking.
///         Helios.md §6.4.
interface IStrategyVault {
    struct Call {
        address target;
        uint256 value;
        bytes data;
    }

    struct StrategyManifest {
        bytes32 declaredClass; // keccak256("momentum_v1") etc.
        address[] assetUniverse;
        uint256 maxCapacity;
        uint16 feeRateBps;
        address operator;
        uint256 stakeAmount;
        // Poseidon commitment to operator-declared circuit parameters
        // (max_position_size, max_slippage_bps, signal_threshold, stop_loss_price).
        // The momentum_v1 circuit recomputes this from its private witnesses
        // and the StrategyVault asserts publicInputs[PI_PARAMS_HASH] matches —
        // so the prover cannot lie about the declared cap / slippage bounds.
        bytes32 paramsHash;
    }

    event TradeAttested(
        address indexed strategy,
        address indexed allocator,
        bytes32 indexed tradeHash,
        bytes32 declaredClass,
        address assetIn,
        address assetOut,
        uint256 amountIn,
        uint256 minAmountOut,
        uint8 direction,
        uint64 blockWindowStart,
        uint64 blockWindowEnd
    );
    event NAVReported(address indexed strategy, uint256 totalNAV, uint64 timestamp);
    event NavClampedOnWithdraw(
        address indexed strategy,
        address indexed allocator,
        uint256 priorTotalNAV,
        uint256 withdrawAmount
    );
    event RealizedDistributed(address indexed strategy, address indexed allocator, uint256 amount);
    event Slashed(address indexed strategy, uint256 amount, string reason);

    error InvalidProof();
    error NotOperator();
    error NotRegistry();
    error AssetNotInUniverse();
    error CapacityExceeded();
    error ClassMismatch();
    error VaultMismatch();
    error AllocatorMismatch();
    error ParamsHashMismatch();

    function executeWithProof(
        bytes calldata proof,
        uint256[] calldata publicInputs,
        Call[] calldata trades
    ) external;

    function allocateFrom(uint256 amount) external;
    function reportNAV(bytes calldata signedNAV) external;
    function distributeRealized(address allocator) external;
    function withdrawToAllocator(address allocator, uint256 amount) external;
    function slash(string calldata reason) external;

    function manifest() external view returns (StrategyManifest memory);
    function totalNAV() external view returns (uint256);
    function navOf(address allocator) external view returns (uint256);
    function allocationOf(address allocator) external view returns (uint256);
}
