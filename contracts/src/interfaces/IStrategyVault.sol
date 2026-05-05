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
        bytes32 declaredClass; // ClassIds.MOMENTUM_V1 etc. (Poseidon-derived; BN254-fit)
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
    /// @notice Emitted when a yield_rotation_v1 trade is attested. The
    ///         private witnesses (signal_threshold, bridging_cost,
    ///         markets_allowlist_root) are committed inside the proof's
    ///         trade_hash but not visible on chain — the audit page
    ///         re-derives them from the prover service.
    event YieldRotationAttested(
        address indexed strategy,
        address indexed allocator,
        bytes32 indexed tradeHash,
        bytes32 declaredClass,
        uint256 mFrom,
        uint256 mTo,
        uint256 amountRotating,
        bytes32 yieldOracleRoot,
        uint64 blockWindowStart,
        uint64 blockWindowEnd
    );

    error InvalidProof();
    error NotOperator();
    error NotRegistry();
    error CapacityExceeded();
    error ClassMismatch();
    error VaultMismatch();
    error AllocatorMismatch();
    error ParamsHashMismatch();
    /// @notice Thrown by the swap path when a `Call.data` selector isn't on
    ///         the trade-call whitelist (`approve` for universe assets,
    ///         `exactInputSingle` for the router). Without this, an operator
    ///         could pass a proof attesting the intent to swap and then ship
    ///         `assetIn.transfer(operator, balance)` as the executed call —
    ///         the proof is theatre for execution. phase2-review.md item 4.
    error TradeCallSelectorNotAllowed();
    /// @notice The `approve` call's spender must equal `allowedRouter`. An
    ///         operator could otherwise grant an allowance to themselves and
    ///         drain the vault via `transferFrom` in a separate tx.
    error ApproveSpenderMismatch();
    /// @notice The `approve` call's amount must equal `publicInputs[PI_AMOUNT_IN]`.
    error ApproveAmountMismatch();
    /// @notice The decoded `exactInputSingle` field doesn't match the proof's
    ///         corresponding public input (`tokenIn`, `tokenOut`, `recipient`,
    ///         `amountIn`, or `amountOutMinimum`). The proof attests the
    ///         intent — the binding ensures execution carries it out.
    error SwapTokenInMismatch();
    error SwapTokenOutMismatch();
    error SwapRecipientMismatch();
    error SwapAmountInMismatch();
    error SwapMinOutMismatch();
    /// @notice yield_rotation_v1 doesn't yet have a calldata-binding circuit
    ///         for cross-chain bridge calls, so the YR entry point requires
    ///         `trades.length == 0` until Phase 5 lands the bridge gadget.
    ///         The proof's `m_from` / `m_to` indices commit the rotation
    ///         intent; execution tracks via the off-chain rotation receipt.
    error YRTradesNotSupported();

    function executeWithProof(
        bytes calldata proof,
        uint256[] calldata publicInputs,
        Call[] calldata trades
    ) external;

    function executeYieldRotationWithProof(
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

    /// @notice Anchors the vault is bound to (set in `initialize`). Exposed
    ///         on the interface so off-chain tooling — e.g. the e2e Phase-2
    ///         oracle commit driver — can route a per-proof commit to the
    ///         exact anchor instance the vault checks against, rather than
    ///         guessing at the deployments-file value (which can shift if
    ///         Phase-2 redeploys an anchor).
    function priceAnchor() external view returns (address);
    function yieldAnchor() external view returns (address);

    /// @notice EIP-712 digest the navOracle is expected to sign for a given
    ///         NAV/timestamp tuple. See `reportNAV` for the typehash and
    ///         domain parameters.
    function navDigest(uint256 totalNAV_, uint64 timestamp) external view returns (bytes32);
}
