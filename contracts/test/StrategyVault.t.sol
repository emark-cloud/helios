// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Test } from "forge-std/Test.sol";
import { ClassIds } from "../src/ClassIds.sol";
import { StrategyVault } from "../src/StrategyVault.sol";
import { IStrategyVault } from "../src/interfaces/IStrategyVault.sol";
import { TradeAttestationVerifier } from "../src/TradeAttestationVerifier.sol";
import { ITradeAttestationVerifier } from "../src/interfaces/ITradeAttestationVerifier.sol";
import { IStrategyRegistry } from "../src/interfaces/IStrategyRegistry.sol";
import { IOracleAnchor } from "../src/interfaces/IOracleAnchor.sol";
import { MockERC20 } from "./mocks/MockERC20.sol";
import { MockGroth16Verifier } from "./mocks/MockGroth16Verifier.sol";
import { ERC1967Proxy } from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";
import { Initializable } from "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";

contract StrategyVaultTest is Test {
    StrategyVault internal impl;
    StrategyVault internal vault;
    TradeAttestationVerifier internal verifier;
    MockGroth16Verifier internal classVerifier;
    MockERC20 internal usdc;
    MockERC20 internal eth;

    address internal owner = makeAddr("owner");
    address internal operator = makeAddr("operator");
    address internal allocatorVault = makeAddr("allocatorVault");
    address internal registry = makeAddr("registry");
    address internal allowedRouter = makeAddr("router");
    address internal priceAnchor = makeAddr("priceAnchor");
    address internal yieldAnchor = makeAddr("yieldAnchor");
    address internal navOracle;
    uint256 internal navOracleKey;
    address internal randomCaller = makeAddr("rando");

    bytes32 internal constant CLASS = ClassIds.MOMENTUM_V1;
    uint256 internal constant MAX_CAPACITY = 1_000_000e18;

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
    event RealizedDistributed(address indexed strategy, address indexed allocator, uint256 amount);
    event Slashed(address indexed strategy, uint256 amount, string reason);

    function setUp() public {
        (navOracle, navOracleKey) = makeAddrAndKey("navOracle");

        usdc = new MockERC20("USDC", "USDC");
        eth = new MockERC20("ETH", "ETH");
        verifier = new TradeAttestationVerifier(owner);
        classVerifier = new MockGroth16Verifier(true);

        vm.prank(owner);
        verifier.registerVerifier(CLASS, address(classVerifier));

        address[] memory universe = new address[](2);
        universe[0] = address(usdc);
        universe[1] = address(eth);
        IStrategyVault.StrategyManifest memory m = IStrategyVault.StrategyManifest({
            declaredClass: CLASS,
            assetUniverse: universe,
            maxCapacity: MAX_CAPACITY,
            feeRateBps: 1000,
            operator: operator,
            stakeAmount: 5000e18,
            paramsHash: bytes32(uint256(0xfee5))
        });

        impl = new StrategyVault();
        StrategyVault.InitParams memory p = StrategyVault.InitParams({
            manifest: m,
            baseAsset: usdc,
            registry: registry,
            verifier: address(verifier),
            allowedRouter: allowedRouter,
            navOracle: navOracle,
            allocatorVault: allocatorVault,
            priceAnchor: priceAnchor,
            yieldAnchor: yieldAnchor,
            owner: owner
        });
        bytes memory initData = abi.encodeCall(StrategyVault.initialize, (p));
        vault = StrategyVault(address(new ERC1967Proxy(address(impl), initData)));

        // Fund allocator vault and approve the strategy vault.
        usdc.mint(allocatorVault, 1_000_000e6);
        vm.prank(allocatorVault);
        usdc.approve(address(vault), type(uint256).max);

        // The vault consults the registry for the active params hash
        // (WS7.A). Tests use a plain EOA for `registry`, so mock the
        // selector to return the manifest hash — the equivalent of
        // having called `commitInitialParamsHash` post-register on the
        // real registry. PR4: the manifest fallback is gone, so a zero
        // return now reverts `ParamsHashNotCommitted`.
        vm.mockCall(
            registry,
            abi.encodeWithSelector(IStrategyRegistry.paramsHashOf.selector),
            abi.encode(bytes32(uint256(0xfee5)))
        );

        // PR1a: vault now binds proofs to roots known to the price/yield
        // anchors (Helios.md §9.3). HIGH #6 — vault now also enforces
        // freshness (180s) via `IOracleAnchor.freshness`. Mock the
        // freshness call to return the current block timestamp so the
        // root is treated as fresh; explicit "unknown root" / "stale
        // root" tests below override.
        vm.mockCall(
            priceAnchor,
            abi.encodeWithSelector(IOracleAnchor.isKnownRoot.selector),
            abi.encode(true)
        );
        vm.mockCall(
            priceAnchor,
            abi.encodeWithSelector(IOracleAnchor.freshness.selector),
            abi.encode(uint64(block.timestamp))
        );
        vm.mockCall(
            yieldAnchor,
            abi.encodeWithSelector(IOracleAnchor.isKnownRoot.selector),
            abi.encode(true)
        );
        vm.mockCall(
            yieldAnchor,
            abi.encodeWithSelector(IOracleAnchor.freshness.selector),
            abi.encode(uint64(block.timestamp))
        );

        // PR2: YR path now binds the proof's `markets_allowlist_root` PI
        // to the registry's per-class allowlist root. Tests use a plain
        // EOA registry, so mock the selector to a deterministic value
        // and reference it from `_yrInputs`. Specific tests override.
        vm.mockCall(
            registry,
            abi.encodeWithSelector(IStrategyRegistry.marketAllowlistRoot.selector),
            abi.encode(bytes32(uint256(0xa11cdef)))
        );
    }

    // ── Initialization ───────────────────────────────────────────────

    function test_Initialize_RevertsOnZeroOperator() public {
        StrategyVault freshImpl = new StrategyVault();
        address[] memory universe = new address[](1);
        universe[0] = address(usdc);
        IStrategyVault.StrategyManifest memory m = IStrategyVault.StrategyManifest({
            declaredClass: CLASS,
            assetUniverse: universe,
            maxCapacity: 1,
            feeRateBps: 0,
            operator: address(0),
            stakeAmount: 0,
            paramsHash: bytes32(0)
        });
        StrategyVault.InitParams memory p = StrategyVault.InitParams({
            manifest: m,
            baseAsset: usdc,
            registry: registry,
            verifier: address(verifier),
            allowedRouter: allowedRouter,
            navOracle: navOracle,
            allocatorVault: allocatorVault,
            priceAnchor: priceAnchor,
            yieldAnchor: yieldAnchor,
            owner: owner
        });
        bytes memory initData = abi.encodeCall(StrategyVault.initialize, (p));
        vm.expectRevert();
        new ERC1967Proxy(address(freshImpl), initData);
    }

    function test_Initialize_RevertsOnSecondCall() public {
        address[] memory universe = new address[](1);
        universe[0] = address(usdc);
        IStrategyVault.StrategyManifest memory m = IStrategyVault.StrategyManifest({
            declaredClass: CLASS,
            assetUniverse: universe,
            maxCapacity: 1,
            feeRateBps: 0,
            operator: operator,
            stakeAmount: 0,
            paramsHash: bytes32(0)
        });
        StrategyVault.InitParams memory p = StrategyVault.InitParams({
            manifest: m,
            baseAsset: usdc,
            registry: registry,
            verifier: address(verifier),
            allowedRouter: allowedRouter,
            navOracle: navOracle,
            allocatorVault: allocatorVault,
            priceAnchor: priceAnchor,
            yieldAnchor: yieldAnchor,
            owner: owner
        });
        vm.expectRevert(Initializable.InvalidInitialization.selector);
        vault.initialize(p);
    }

    function test_Initialize_DisablesOnImplementation() public {
        address[] memory universe = new address[](1);
        universe[0] = address(usdc);
        IStrategyVault.StrategyManifest memory m = IStrategyVault.StrategyManifest({
            declaredClass: CLASS,
            assetUniverse: universe,
            maxCapacity: 1,
            feeRateBps: 0,
            operator: operator,
            stakeAmount: 0,
            paramsHash: bytes32(0)
        });
        StrategyVault.InitParams memory p = StrategyVault.InitParams({
            manifest: m,
            baseAsset: usdc,
            registry: registry,
            verifier: address(verifier),
            allowedRouter: allowedRouter,
            navOracle: navOracle,
            allocatorVault: allocatorVault,
            priceAnchor: priceAnchor,
            yieldAnchor: yieldAnchor,
            owner: owner
        });
        vm.expectRevert(Initializable.InvalidInitialization.selector);
        impl.initialize(p);
    }

    // ── allocateFrom ────────────────────────────────────────────────

    function test_AllocateFrom_OnlyAllocatorVault() public {
        vm.prank(randomCaller);
        vm.expectRevert(StrategyVault.NotAllocatorVault.selector);
        vault.allocateFrom(100e6);
    }

    function test_AllocateFrom_RevertsOnZeroAmount() public {
        vm.prank(allocatorVault);
        vm.expectRevert(StrategyVault.AmountInMismatch.selector);
        vault.allocateFrom(0);
    }

    function test_AllocateFrom_TransfersAndAccrues() public {
        vm.prank(allocatorVault);
        vault.allocateFrom(100e6);
        assertEq(usdc.balanceOf(address(vault)), 100e6);
        assertEq(vault.allocationOf(allocatorVault), 100e6);
        assertEq(vault.totalNAV(), 100e6);
    }

    function test_AllocateFrom_RevertsOnCapacity() public {
        usdc.mint(allocatorVault, MAX_CAPACITY + 1);
        vm.prank(allocatorVault);
        vm.expectRevert(IStrategyVault.CapacityExceeded.selector);
        vault.allocateFrom(MAX_CAPACITY + 1);
    }

    function test_AllocateFrom_RevertsWhenHalted() public {
        vm.prank(registry);
        vault.slash("test halt");
        vm.prank(allocatorVault);
        vm.expectRevert(StrategyVault.VaultHalted.selector);
        vault.allocateFrom(1);
    }

    // ── withdrawToAllocator ─────────────────────────────────────────

    function test_WithdrawToAllocator_OnlyAllocatorVault() public {
        vm.prank(randomCaller);
        vm.expectRevert(StrategyVault.NotAllocatorVault.selector);
        vault.withdrawToAllocator(allocatorVault, 1);
    }

    function test_WithdrawToAllocator_RevertsOnOverdraw() public {
        vm.prank(allocatorVault);
        vault.allocateFrom(100e6);
        vm.prank(allocatorVault);
        vm.expectRevert(StrategyVault.AllocationOverdrawn.selector);
        vault.withdrawToAllocator(allocatorVault, 100e6 + 1);
    }

    function test_WithdrawToAllocator_HappyPath() public {
        vm.prank(allocatorVault);
        vault.allocateFrom(500e6);
        uint256 balBefore = usdc.balanceOf(allocatorVault);

        vm.prank(allocatorVault);
        vault.withdrawToAllocator(allocatorVault, 200e6);

        assertEq(vault.allocationOf(allocatorVault), 300e6);
        assertEq(vault.totalNAV(), 300e6);
        assertEq(usdc.balanceOf(allocatorVault), balBefore + 200e6);
    }

    // ── distributeRealized ──────────────────────────────────────────

    function test_DistributeRealized_NoOpWhenUnderwater() public {
        vm.prank(allocatorVault);
        vault.allocateFrom(1000e6);
        // Without a NAV report, share == principal => no-op.
        vm.expectEmit(true, true, false, true);
        emit RealizedDistributed(address(vault), allocatorVault, 0);
        vm.prank(allocatorVault);
        vault.distributeRealized(allocatorVault);
    }

    function test_DistributeRealized_PaysOutPnL() public {
        vm.prank(allocatorVault);
        vault.allocateFrom(1000e6);
        // Simulate the strategy gained 200 USDC via off-chain trading.
        usdc.mint(address(vault), 200e6);
        _reportNAV(1200e6, uint64(block.timestamp + 1));

        uint256 balBefore = usdc.balanceOf(allocatorVault);
        vm.expectEmit(true, true, false, true);
        emit RealizedDistributed(address(vault), allocatorVault, 200e6);
        vm.prank(allocatorVault);
        vault.distributeRealized(allocatorVault);

        assertEq(usdc.balanceOf(allocatorVault), balBefore + 200e6);
        assertEq(vault.totalNAV(), 1000e6);
        assertEq(vault.allocationOf(allocatorVault), 1000e6);
    }

    // ── executeWithProof ────────────────────────────────────────────

    function _proofBytes() internal pure returns (bytes memory) {
        uint256[2] memory a = [uint256(1), 2];
        uint256[2][2] memory b = [[uint256(3), 4], [uint256(5), 6]];
        uint256[2] memory c = [uint256(7), 8];
        return abi.encode(a, b, c);
    }

    function _validInputs() internal view returns (uint256[] memory pi) {
        // Layout matches StrategyVault.PI_*:
        //  [0] trade_hash
        //  [1] declared_class
        //  [2] strategy_vault
        //  [3] params_hash
        //  [4] allocator
        //  [5] asset_in_idx
        //  [6] asset_out_idx
        //  [7] amount_in
        //  [8] min_amount_out
        //  [9] direction
        //  [10] nonce
        //  [11] block_window_start
        //  [12] block_window_end
        //  [13] oracle_root
        pi = new uint256[](14);
        pi[0] = uint256(keccak256("trade-1"));
        pi[1] = uint256(CLASS);
        pi[2] = uint256(uint160(address(vault)));
        pi[3] = uint256(bytes32(uint256(0xfee5))); // matches setUp paramsHash
        pi[4] = uint256(uint160(allocatorVault));
        pi[5] = 0; // asset_in_idx → USDC
        pi[6] = 1; // asset_out_idx → ETH
        pi[7] = 100e6; // amount_in
        pi[8] = 1e16; // min_amount_out
        pi[9] = 1; // direction (enter)
        pi[10] = 1; // nonce
        pi[11] = block.number; // window_start
        pi[12] = block.number + 10; // window_end
        pi[13] = uint256(keccak256("oracle-root-1"));
    }

    function test_ExecuteWithProof_OnlyOperator() public {
        uint256[] memory pi = _validInputs();
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](0);
        vm.prank(randomCaller);
        vm.expectRevert(IStrategyVault.NotOperator.selector);
        vault.executeWithProof(_proofBytes(), pi, trades);
    }

    function test_ExecuteWithProof_RevertsOnShortInputs() public {
        uint256[] memory pi = new uint256[](13);
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](0);
        vm.prank(operator);
        vm.expectRevert(StrategyVault.PublicInputsTooShort.selector);
        vault.executeWithProof(_proofBytes(), pi, trades);
    }

    function test_ExecuteWithProof_RevertsOnAssetOOB() public {
        uint256[] memory pi = _validInputs();
        pi[5] = 99;
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](0);
        vm.prank(operator);
        vm.expectRevert(StrategyVault.AssetIndexOOB.selector);
        vault.executeWithProof(_proofBytes(), pi, trades);
    }

    function test_ExecuteWithProof_RevertsOnClassMismatch() public {
        uint256[] memory pi = _validInputs();
        pi[1] = uint256(keccak256("wrong_class"));
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](0);
        vm.prank(operator);
        vm.expectRevert(IStrategyVault.ClassMismatch.selector);
        vault.executeWithProof(_proofBytes(), pi, trades);
    }

    function test_ExecuteWithProof_RevertsOnVaultMismatch() public {
        uint256[] memory pi = _validInputs();
        pi[2] = uint256(uint160(randomCaller));
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](0);
        vm.prank(operator);
        vm.expectRevert(IStrategyVault.VaultMismatch.selector);
        vault.executeWithProof(_proofBytes(), pi, trades);
    }

    function test_ExecuteWithProof_RevertsOnParamsHashMismatch() public {
        uint256[] memory pi = _validInputs();
        pi[3] = uint256(bytes32(uint256(0xdead)));
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](0);
        vm.prank(operator);
        vm.expectRevert(IStrategyVault.ParamsHashMismatch.selector);
        vault.executeWithProof(_proofBytes(), pi, trades);
    }

    function test_ExecuteWithProof_RevertsOnAllocatorMismatch() public {
        uint256[] memory pi = _validInputs();
        pi[4] = uint256(uint160(randomCaller));
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](0);
        vm.prank(operator);
        vm.expectRevert(IStrategyVault.AllocatorMismatch.selector);
        vault.executeWithProof(_proofBytes(), pi, trades);
    }

    function test_ExecuteWithProof_RevertsOnWindowNotStarted() public {
        uint256[] memory pi = _validInputs();
        pi[11] = block.number + 5;
        pi[12] = block.number + 10;
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](0);
        vm.prank(operator);
        vm.expectRevert(StrategyVault.WindowNotStarted.selector);
        vault.executeWithProof(_proofBytes(), pi, trades);
    }

    function test_ExecuteWithProof_RevertsOnWindowExpired() public {
        uint256[] memory pi = _validInputs();
        pi[11] = block.number;
        pi[12] = block.number;
        vm.roll(block.number + 1);
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](0);
        vm.prank(operator);
        vm.expectRevert(StrategyVault.WindowExpired.selector);
        vault.executeWithProof(_proofBytes(), pi, trades);
    }

    function test_ExecuteWithProof_RevertsOnReplayedTradeHash() public {
        uint256[] memory pi = _validInputs();
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](0);
        vm.prank(operator);
        vault.executeWithProof(_proofBytes(), pi, trades);

        vm.prank(operator);
        vm.expectRevert(StrategyVault.TradeAlreadySettled.selector);
        vault.executeWithProof(_proofBytes(), pi, trades);
    }

    function test_ExecuteWithProof_RevertsOnBadProof() public {
        classVerifier.setAnswer(false);
        uint256[] memory pi = _validInputs();
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](0);
        vm.prank(operator);
        vm.expectRevert(IStrategyVault.InvalidProof.selector);
        vault.executeWithProof(_proofBytes(), pi, trades);
    }

    function test_ExecuteWithProof_RevertsOnUnknownOracleRoot() public {
        // Anchor disowns the proof's oracle root → revert before verifier call.
        // PR1a hardening — without the binding the prover can mint a Poseidon
        // root over fictitious prices and pass the on-chain verifier. HIGH #6
        // — `freshness` returning 0 stands in for both "never committed" and
        // "currently revoked"; either way the vault must refuse the trade.
        vm.mockCall(
            priceAnchor,
            abi.encodeWithSelector(IOracleAnchor.freshness.selector),
            abi.encode(uint64(0))
        );
        uint256[] memory pi = _validInputs();
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](0);
        vm.prank(operator);
        vm.expectRevert(StrategyVault.UnknownOracleRoot.selector);
        vault.executeWithProof(_proofBytes(), pi, trades);
    }

    function test_ExecuteWithProof_RevertsOnStaleOracleRoot() public {
        // HIGH #6 — a root committed > _MAX_ORACLE_STALENESS_SEC (180s)
        // ago must not justify a fresh trade. Anchor reports a known
        // root with a long-past committedAt timestamp.
        vm.warp(10_000); // anchor block.timestamp set during setUp() = 1
        vm.mockCall(
            priceAnchor,
            abi.encodeWithSelector(IOracleAnchor.freshness.selector),
            abi.encode(uint64(10_000 - 200)) // 200s ago — outside the 180s window
        );
        uint256[] memory pi = _validInputs();
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](0);
        vm.prank(operator);
        vm.expectRevert(StrategyVault.OracleRootStale.selector);
        vault.executeWithProof(_proofBytes(), pi, trades);
    }

    function test_ExecuteWithProof_QueriesAnchorWithProvenRoot() public {
        // The vault must call freshness with the exact bytes32 from
        // publicInputs[PI_ORACLE_ROOT], not some derived value.
        uint256[] memory pi = _validInputs();
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](0);
        vm.expectCall(
            priceAnchor, abi.encodeWithSelector(IOracleAnchor.freshness.selector, bytes32(pi[13]))
        );
        vm.prank(operator);
        vault.executeWithProof(_proofBytes(), pi, trades);
    }

    function test_ExecuteWithProof_RevertsOnCallNonZeroValue() public {
        uint256[] memory pi = _validInputs();
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](1);
        trades[0] = IStrategyVault.Call({ target: allowedRouter, value: 1, data: "" });
        vm.prank(operator);
        vm.expectRevert(StrategyVault.NonZeroValue.selector);
        vault.executeWithProof(_proofBytes(), pi, trades);
    }

    function test_ExecuteWithProof_RevertsOnWrongTarget() public {
        uint256[] memory pi = _validInputs();
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](1);
        trades[0] = IStrategyVault.Call({ target: randomCaller, value: 0, data: "" });
        vm.prank(operator);
        vm.expectRevert(StrategyVault.WrongTarget.selector);
        vault.executeWithProof(_proofBytes(), pi, trades);
    }

    function test_ExecuteWithProof_AllowsAssetApproval() public {
        uint256[] memory pi = _validInputs();
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](1);
        // approve(allowedRouter, amountIn) on assetIn — a normal swap setup call
        trades[0] = IStrategyVault.Call({
            target: address(usdc),
            value: 0,
            data: abi.encodeWithSignature("approve(address,uint256)", allowedRouter, 100e6)
        });
        vm.prank(operator);
        vault.executeWithProof(_proofBytes(), pi, trades);
        assertEq(usdc.allowance(address(vault), allowedRouter), 100e6);
    }

    function test_ExecuteWithProof_EmitsTradeAttested() public {
        uint256[] memory pi = _validInputs();
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](0);
        vm.expectEmit(true, true, true, true);
        emit TradeAttested(
            address(vault),
            allocatorVault,
            bytes32(pi[0]),
            CLASS,
            address(usdc),
            address(eth),
            100e6,
            1e16,
            1,
            uint64(pi[11]),
            uint64(pi[12])
        );
        vm.prank(operator);
        vault.executeWithProof(_proofBytes(), pi, trades);
        assertTrue(vault.isTradeHashSeen(bytes32(pi[0])));
    }

    function test_ExecuteWithProof_RevertsWhenHalted() public {
        vm.prank(registry);
        vault.slash("halt");
        uint256[] memory pi = _validInputs();
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](0);
        vm.prank(operator);
        vm.expectRevert(StrategyVault.VaultHalted.selector);
        vault.executeWithProof(_proofBytes(), pi, trades);
    }

    // ── reportNAV ──────────────────────────────────────────────────

    function _reportNAV(uint256 nav, uint64 ts) internal {
        bytes memory sig = _signNAV(vault, nav, ts);
        vm.prank(operator);
        vault.reportNAV(abi.encode(nav, ts, sig));
    }

    function _signNAV(StrategyVault v_, uint256 nav, uint64 ts)
        internal
        view
        returns (bytes memory)
    {
        bytes32 digest = v_.navDigest(nav, ts);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(navOracleKey, digest);
        return abi.encodePacked(r, s, v);
    }

    function test_ReportNAV_HappyPath() public {
        uint64 ts = uint64(block.timestamp + 1);
        vm.expectEmit(true, false, false, true);
        emit NAVReported(address(vault), 1234e6, ts);
        _reportNAV(1234e6, ts);
        assertEq(vault.totalNAV(), 1234e6);
        assertEq(vault.lastNAVTimestamp(), ts);
    }

    function test_ReportNAV_RevertsOnStaleTimestamp() public {
        uint64 ts = uint64(block.timestamp + 1);
        _reportNAV(1000e6, ts);
        // Pre-compute the second sig outside expectRevert so the staticcall
        // to `navDigest` doesn't consume the expectation slot.
        bytes memory sig2 = _signNAV(vault, 1500e6, ts);
        vm.expectRevert(StrategyVault.StaleNav.selector);
        vm.prank(operator);
        vault.reportNAV(abi.encode(uint256(1500e6), ts, sig2));
    }

    function test_ReportNAV_RevertsOnBadSigner() public {
        uint64 ts = uint64(block.timestamp + 1);
        (, uint256 wrongKey) = makeAddrAndKey("wrongOracle");
        bytes32 digest = vault.navDigest(1000e6, ts);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(wrongKey, digest);
        bytes memory sig = abi.encodePacked(r, s, v);
        vm.expectRevert(StrategyVault.NavSignatureInvalid.selector);
        vm.prank(operator);
        vault.reportNAV(abi.encode(uint256(1000e6), ts, sig));
    }

    function test_ReportNAV_RevertsAboveCap() public {
        uint64 ts = uint64(block.timestamp + 1);
        // 10× MAX_CAPACITY is the bound; one wei above must revert.
        uint256 over = 10 * MAX_CAPACITY + 1;
        bytes memory sig = _signNAV(vault, over, ts);
        vm.expectRevert(StrategyVault.NavExceedsCap.selector);
        vm.prank(operator);
        vault.reportNAV(abi.encode(over, ts, sig));
    }

    function test_ReportNAV_AcceptsAtCap() public {
        uint64 ts = uint64(block.timestamp + 1);
        uint256 atCap = 10 * MAX_CAPACITY;
        _reportNAV(atCap, ts);
        assertEq(vault.totalNAV(), atCap);
    }

    function test_ReportNAV_RevertsOnLegacyRawDigest() public {
        // Pre-PR1b raw signing format must be rejected — proves cross-vault
        // and cross-chain replay protection now hangs off the EIP-712 domain
        // rather than the inlined chainid + verifyingContract values.
        uint64 ts = uint64(block.timestamp + 1);
        bytes32 legacyDigest =
            keccak256(abi.encode(block.chainid, address(vault), uint256(1000e6), ts));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(navOracleKey, legacyDigest);
        bytes memory sig = abi.encodePacked(r, s, v);
        vm.expectRevert(StrategyVault.NavSignatureInvalid.selector);
        vm.prank(operator);
        vault.reportNAV(abi.encode(uint256(1000e6), ts, sig));
    }

    function test_ReportNAV_RevertsWhenCallerNotOperatorOrNavOracle() public {
        // HIGH #7 — caller restriction. Even with a valid signature, an
        // arbitrary EOA must not be able to land a NAV update; that lets
        // an MEV bot front-run the operator's submission with a stale-
        // but-valid signature.
        uint64 ts = uint64(block.timestamp + 1);
        bytes memory sig = _signNAV(vault, 1000e6, ts);
        vm.prank(makeAddr("stranger"));
        vm.expectRevert(StrategyVault.NotOperatorOrNavOracle.selector);
        vault.reportNAV(abi.encode(uint256(1000e6), ts, sig));
    }

    function test_ReportNAV_AcceptsNavOracleAsCaller() public {
        // The navOracle itself may submit (so a Helios-operated submitter
        // can post directly without round-tripping through the strategy
        // operator).
        uint64 ts = uint64(block.timestamp + 1);
        bytes memory sig = _signNAV(vault, 1234e6, ts);
        vm.prank(navOracle);
        vault.reportNAV(abi.encode(uint256(1234e6), ts, sig));
        assertEq(vault.totalNAV(), 1234e6);
    }

    function test_ReportNAV_RevertsOnTooOldSignature() public {
        // HIGH #7 — bounded replay window. A signature whose `timestamp`
        // is outside `_MAX_NAV_AGE_SEC` (600s) of `block.timestamp` must
        // be refused even when monotonicity is satisfied.
        uint64 oldTs = uint64(block.timestamp + 1);
        bytes memory sig = _signNAV(vault, 1000e6, oldTs);
        // Fast-forward past the age window. _MAX_NAV_AGE_SEC = 600s.
        vm.warp(block.timestamp + 700);
        vm.expectRevert(StrategyVault.NavTooOld.selector);
        vm.prank(operator);
        vault.reportNAV(abi.encode(uint256(1000e6), oldTs, sig));
    }

    function test_ReportNAV_AcceptsAtAgeBoundary() public {
        // A signature exactly at the age boundary must still be accepted
        // — the gate is `block.timestamp > timestamp + _MAX_NAV_AGE_SEC`,
        // strictly greater than. Locks in the inclusive boundary.
        uint64 ts = uint64(block.timestamp + 1);
        bytes memory sig = _signNAV(vault, 1000e6, ts);
        vm.warp(uint256(ts) + 600);
        vm.prank(operator);
        vault.reportNAV(abi.encode(uint256(1000e6), ts, sig));
        assertEq(vault.totalNAV(), 1000e6);
    }

    function test_ReportNAV_RejectsCrossVaultReplay() public {
        // Sign a NAV update for `vault`, then deploy a sibling vault and
        // confirm the same signature is rejected there. EIP-712 binds the
        // digest to `verifyingContract` so reuse is impossible.
        uint64 ts = uint64(block.timestamp + 1);
        bytes32 digest = vault.navDigest(1000e6, ts);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(navOracleKey, digest);
        bytes memory sig = abi.encodePacked(r, s, v);

        // Spin up a sibling vault with the same navOracle.
        StrategyVault sibling;
        {
            address[] memory universe = new address[](1);
            universe[0] = address(usdc);
            IStrategyVault.StrategyManifest memory m = IStrategyVault.StrategyManifest({
                declaredClass: CLASS,
                assetUniverse: universe,
                maxCapacity: MAX_CAPACITY,
                feeRateBps: 1000,
                operator: operator,
                stakeAmount: 5000e18,
                paramsHash: bytes32(uint256(0xfee5))
            });
            StrategyVault siblingImpl = new StrategyVault();
            StrategyVault.InitParams memory p = StrategyVault.InitParams({
                manifest: m,
                baseAsset: usdc,
                registry: registry,
                verifier: address(verifier),
                allowedRouter: allowedRouter,
                navOracle: navOracle,
                allocatorVault: allocatorVault,
                priceAnchor: priceAnchor,
                yieldAnchor: yieldAnchor,
                owner: owner
            });
            bytes memory initData = abi.encodeCall(StrategyVault.initialize, (p));
            sibling = StrategyVault(address(new ERC1967Proxy(address(siblingImpl), initData)));
        }

        vm.expectRevert(StrategyVault.NavSignatureInvalid.selector);
        vm.prank(operator);
        sibling.reportNAV(abi.encode(uint256(1000e6), ts, sig));
    }

    // ── slash ──────────────────────────────────────────────────────

    function test_Slash_OnlyRegistry() public {
        vm.prank(randomCaller);
        vm.expectRevert(IStrategyVault.NotRegistry.selector);
        vault.slash("rug");
    }

    function test_Slash_HaltsAndEmits() public {
        vm.expectEmit(true, false, false, true);
        emit Slashed(address(vault), 0, "rug");
        vm.prank(registry);
        vault.slash("rug");
        assertTrue(vault.halted());
    }

    // ── Views ──────────────────────────────────────────────────────

    function test_NavOf_ScalesWithReportedNAV() public {
        vm.prank(allocatorVault);
        vault.allocateFrom(1000e6);
        // After a 50% gain
        usdc.mint(address(vault), 500e6);
        _reportNAV(1500e6, uint64(block.timestamp + 1));
        assertEq(vault.navOf(allocatorVault), 1500e6);
    }

    function test_Manifest_ReturnsConfig() public view {
        IStrategyVault.StrategyManifest memory m = vault.manifest();
        assertEq(m.declaredClass, CLASS);
        assertEq(m.operator, operator);
        assertEq(m.maxCapacity, MAX_CAPACITY);
        assertEq(m.assetUniverse.length, 2);
    }

    // ── WS7.A: registry-pulled params hash overrides manifest ──────

    function test_ExecuteWithProof_RevertsWhenParamsHashNotCommitted() public {
        // No commit on the registry yet ⇒ paramsHashOf returns 0. PR4
        // removed the manifest fallback, so the vault must reject any
        // trade attempt before even checking the proof's PI value.
        vm.mockCall(
            registry,
            abi.encodeWithSelector(IStrategyRegistry.paramsHashOf.selector),
            abi.encode(bytes32(0))
        );

        uint256[] memory pi = _validInputs();
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](0);
        vm.prank(operator);
        vm.expectRevert(StrategyVault.ParamsHashNotCommitted.selector);
        vault.executeWithProof(_proofBytes(), pi, trades);
    }

    function test_ExecuteWithProof_UsesRegistryParamsHashWhenCommitted() public {
        bytes32 newHash = keccak256("rotated-params-v2");
        // Registry now returns the rotated hash; the proof's PI_PARAMS_HASH
        // must match this value, not the manifest's 0xfee5 default.
        vm.mockCall(
            registry,
            abi.encodeWithSelector(IStrategyRegistry.paramsHashOf.selector),
            abi.encode(newHash)
        );

        uint256[] memory pi = _validInputs();
        // First confirm the old (manifest) hash is now rejected.
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](0);
        vm.prank(operator);
        vm.expectRevert(IStrategyVault.ParamsHashMismatch.selector);
        vault.executeWithProof(_proofBytes(), pi, trades);

        // Then confirm the rotated hash passes.
        pi[3] = uint256(newHash);
        vm.prank(operator);
        vault.executeWithProof(_proofBytes(), pi, trades);
    }

    // ── PR2: yield-rotation 12-PI entry path ───────────────────────

    bytes32 internal constant _YR_ALLOWLIST_ROOT = bytes32(uint256(0xa11cdef));

    function _yrInputs() internal view returns (uint256[] memory pi) {
        // Layout (must match circuits/yield_rotation_v1.circom):
        //  [0]  trade_hash
        //  [1]  declared_class
        //  [2]  strategy_vault       (vault checks address(this) equality)
        //  [3]  params_hash          (vault checks _activeParamsHash())
        //  [4]  markets_allowlist_root (vault checks
        //                              StrategyRegistry.marketAllowlistRoot(class))
        //  [5]  m_from
        //  [6]  m_to
        //  [7]  amount_rotating
        //  [8]  yield_oracle_root
        //  [9]  allocator
        //  [10] nonce
        //  [11] block_window_end
        //  [12] block_window_start
        pi = new uint256[](13);
        pi[0] = uint256(keccak256("yr-trade-1"));
        pi[1] = uint256(CLASS);
        pi[2] = uint256(uint160(address(vault)));
        pi[3] = uint256(bytes32(uint256(0xfee5))); // matches setUp manifest paramsHash
        pi[4] = uint256(_YR_ALLOWLIST_ROOT);
        pi[5] = 1; // m_from market id
        pi[6] = 2; // m_to market id
        pi[7] = 1000e6; // amount rotating
        pi[8] = uint256(keccak256("yield-oracle-root"));
        pi[9] = uint256(uint160(allocatorVault));
        pi[10] = 7; // nonce
        pi[11] = block.number + 10;
        pi[12] = block.number;
    }

    function test_ExecuteYieldRotationWithProof_HappyPath() public {
        uint256[] memory pi = _yrInputs();
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](0);

        vm.expectEmit(true, true, true, true);
        emit IStrategyVault.YieldRotationAttested(
            address(vault),
            allocatorVault,
            bytes32(pi[0]),
            CLASS,
            pi[5],
            pi[6],
            pi[7],
            bytes32(pi[8]),
            uint64(pi[12]),
            uint64(pi[11])
        );
        vm.prank(operator);
        vault.executeYieldRotationWithProof(_proofBytes(), pi, trades);
    }

    function test_ExecuteYieldRotationWithProof_RevertsOnShortInputs() public {
        uint256[] memory pi = new uint256[](12);
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](0);
        vm.prank(operator);
        vm.expectRevert(StrategyVault.PublicInputsTooShort.selector);
        vault.executeYieldRotationWithProof(_proofBytes(), pi, trades);
    }

    function test_ExecuteYieldRotationWithProof_RevertsOnClassMismatch() public {
        uint256[] memory pi = _yrInputs();
        pi[1] = uint256(keccak256("other_class"));
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](0);
        vm.prank(operator);
        vm.expectRevert(IStrategyVault.ClassMismatch.selector);
        vault.executeYieldRotationWithProof(_proofBytes(), pi, trades);
    }

    function test_ExecuteYieldRotationWithProof_RevertsOnVaultMismatch() public {
        uint256[] memory pi = _yrInputs();
        // Operator points the proof at a sibling vault address (cross-vault
        // replay attempt). PR2 / phase2-review.md C-2.
        pi[2] = uint256(uint160(makeAddr("siblingYrVault")));
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](0);
        vm.prank(operator);
        vm.expectRevert(IStrategyVault.VaultMismatch.selector);
        vault.executeYieldRotationWithProof(_proofBytes(), pi, trades);
    }

    function test_ExecuteYieldRotationWithProof_RevertsOnParamsHashMismatch() public {
        uint256[] memory pi = _yrInputs();
        // Stale or shifted operator-declared (signal_threshold, bridging_cost)
        // commitment — vault rejects before the verifier. PR2 / C-3.
        pi[3] = uint256(keccak256("stale-params"));
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](0);
        vm.prank(operator);
        vm.expectRevert(IStrategyVault.ParamsHashMismatch.selector);
        vault.executeYieldRotationWithProof(_proofBytes(), pi, trades);
    }

    function test_ExecuteYieldRotationWithProof_RevertsOnAllowlistMismatch() public {
        uint256[] memory pi = _yrInputs();
        // Operator claims a different allowlist root than the registry
        // committed — `setMarketAllowlistRoot` becomes load-bearing here.
        // PR2 / C-3.
        pi[4] = uint256(keccak256("rogue-allowlist"));
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](0);
        vm.prank(operator);
        vm.expectRevert(StrategyVault.AllowlistRootMismatch.selector);
        vault.executeYieldRotationWithProof(_proofBytes(), pi, trades);
    }

    function test_ExecuteYieldRotationWithProof_RevertsOnAllocatorMismatch() public {
        uint256[] memory pi = _yrInputs();
        pi[9] = uint256(uint160(makeAddr("notAllocator")));
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](0);
        vm.prank(operator);
        vm.expectRevert(IStrategyVault.AllocatorMismatch.selector);
        vault.executeYieldRotationWithProof(_proofBytes(), pi, trades);
    }

    function test_ExecuteYieldRotationWithProof_RevertsOnWindowExpired() public {
        uint256[] memory pi = _yrInputs();
        pi[11] = block.number == 0 ? 0 : block.number - 1;
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](0);
        vm.prank(operator);
        vm.expectRevert(StrategyVault.WindowExpired.selector);
        vault.executeYieldRotationWithProof(_proofBytes(), pi, trades);
    }

    function test_ExecuteYieldRotationWithProof_RevertsOnReplay() public {
        uint256[] memory pi = _yrInputs();
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](0);
        vm.prank(operator);
        vault.executeYieldRotationWithProof(_proofBytes(), pi, trades);

        vm.prank(operator);
        vm.expectRevert(StrategyVault.TradeAlreadySettled.selector);
        vault.executeYieldRotationWithProof(_proofBytes(), pi, trades);
    }

    function test_ExecuteYieldRotationWithProof_RevertsOnBadProof() public {
        // Re-deploy a verifier that returns false to force the InvalidProof path.
        MockGroth16Verifier badInner = new MockGroth16Verifier(false);
        vm.prank(owner);
        verifier.registerVerifier(CLASS, address(badInner));

        uint256[] memory pi = _yrInputs();
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](0);
        vm.prank(operator);
        vm.expectRevert(IStrategyVault.InvalidProof.selector);
        vault.executeYieldRotationWithProof(_proofBytes(), pi, trades);
    }

    function test_ExecuteYieldRotationWithProof_OnlyOperator() public {
        uint256[] memory pi = _yrInputs();
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](0);
        vm.prank(randomCaller);
        vm.expectRevert(IStrategyVault.NotOperator.selector);
        vault.executeYieldRotationWithProof(_proofBytes(), pi, trades);
    }

    function test_ExecuteYieldRotationWithProof_RevertsOnUnknownYieldRoot() public {
        // Yield-anchor disowns the proof's yield_oracle_root → revert before
        // the verifier is consulted. Mirror of the price-side anchor binding.
        vm.mockCall(
            yieldAnchor,
            abi.encodeWithSelector(IOracleAnchor.isKnownRoot.selector),
            abi.encode(false)
        );
        uint256[] memory pi = _yrInputs();
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](0);
        vm.prank(operator);
        vm.expectRevert(StrategyVault.UnknownYieldOracleRoot.selector);
        vault.executeYieldRotationWithProof(_proofBytes(), pi, trades);
    }

    // ── PR3: trade calldata bound to the proof ─────────────────────
    //
    // The proof attests intent (assetIn/assetOut/amountIn/minOut). Without
    // these checks the operator could pass `assetIn.transfer(operator, ...)`
    // as the executed call and drain the vault while still emitting a valid
    // TradeAttested. phase2-review.md item 4.

    bytes4 internal constant _EXACT_INPUT_SINGLE_SELECTOR = bytes4(
        keccak256("exactInputSingle((address,address,address,uint256,uint256,uint256,uint160))")
    );

    function _validSwapCalldata(uint256[] memory pi) internal view returns (bytes memory) {
        return abi.encodeWithSelector(
            _EXACT_INPUT_SINGLE_SELECTOR,
            address(usdc), // tokenIn (matches pi[5]=0 → universe[0])
            address(eth), // tokenOut (matches pi[6]=1 → universe[1])
            address(vault), // recipient
            uint256(block.timestamp + 1), // deadline (operational, not bound)
            pi[7], // amountIn
            pi[8], // amountOutMinimum
            uint160(0) // limitSqrtPrice (operational, not bound)
        );
    }

    function test_ExecuteWithProof_AllowsValidSwap() public {
        uint256[] memory pi = _validInputs();
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](2);
        // Step 1: approve assetIn -> router for amountIn
        trades[0] = IStrategyVault.Call({
            target: address(usdc),
            value: 0,
            data: abi.encodeWithSignature("approve(address,uint256)", allowedRouter, pi[7])
        });
        // Step 2: exactInputSingle on the router with proof-bound fields
        trades[1] =
            IStrategyVault.Call({ target: allowedRouter, value: 0, data: _validSwapCalldata(pi) });
        // Allow the router call to succeed (it's an EOA in this test).
        vm.mockCall(allowedRouter, trades[1].data, abi.encode(uint256(0)));
        vm.prank(operator);
        vault.executeWithProof(_proofBytes(), pi, trades);
        assertEq(usdc.allowance(address(vault), allowedRouter), pi[7]);
    }

    function test_ExecuteWithProof_RevertsOnApproveSpenderMismatch() public {
        uint256[] memory pi = _validInputs();
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](1);
        trades[0] = IStrategyVault.Call({
            target: address(usdc),
            value: 0,
            data: abi.encodeWithSignature("approve(address,uint256)", operator, pi[7])
        });
        vm.prank(operator);
        vm.expectRevert(IStrategyVault.ApproveSpenderMismatch.selector);
        vault.executeWithProof(_proofBytes(), pi, trades);
    }

    function test_ExecuteWithProof_RevertsOnApproveAmountMismatch() public {
        uint256[] memory pi = _validInputs();
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](1);
        trades[0] = IStrategyVault.Call({
            target: address(usdc),
            value: 0,
            data: abi.encodeWithSignature("approve(address,uint256)", allowedRouter, pi[7] + 1)
        });
        vm.prank(operator);
        vm.expectRevert(IStrategyVault.ApproveAmountMismatch.selector);
        vault.executeWithProof(_proofBytes(), pi, trades);
    }

    function test_ExecuteWithProof_RevertsOnAssetTransferAttempt() public {
        // Operator tries to drain the vault by smuggling a transfer() call
        // on a universe asset. The selector whitelist rejects it.
        uint256[] memory pi = _validInputs();
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](1);
        trades[0] = IStrategyVault.Call({
            target: address(usdc),
            value: 0,
            data: abi.encodeWithSignature("transfer(address,uint256)", operator, 100e6)
        });
        vm.prank(operator);
        vm.expectRevert(IStrategyVault.TradeCallSelectorNotAllowed.selector);
        vault.executeWithProof(_proofBytes(), pi, trades);
    }

    function test_ExecuteWithProof_RevertsOnRouterUnknownSelector() public {
        uint256[] memory pi = _validInputs();
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](1);
        trades[0] = IStrategyVault.Call({
            target: allowedRouter,
            value: 0,
            data: abi.encodeWithSignature("multicall(bytes[])", new bytes[](0))
        });
        vm.prank(operator);
        vm.expectRevert(IStrategyVault.TradeCallSelectorNotAllowed.selector);
        vault.executeWithProof(_proofBytes(), pi, trades);
    }

    function test_ExecuteWithProof_RevertsOnSwapTokenInMismatch() public {
        uint256[] memory pi = _validInputs();
        bytes memory data = abi.encodeWithSelector(
            _EXACT_INPUT_SINGLE_SELECTOR,
            address(eth), // wrong tokenIn (PI says assetIn = USDC)
            address(eth),
            address(vault),
            uint256(block.timestamp + 1),
            pi[7],
            pi[8],
            uint160(0)
        );
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](1);
        trades[0] = IStrategyVault.Call({ target: allowedRouter, value: 0, data: data });
        vm.prank(operator);
        vm.expectRevert(IStrategyVault.SwapTokenInMismatch.selector);
        vault.executeWithProof(_proofBytes(), pi, trades);
    }

    function test_ExecuteWithProof_RevertsOnSwapTokenOutMismatch() public {
        uint256[] memory pi = _validInputs();
        bytes memory data = abi.encodeWithSelector(
            _EXACT_INPUT_SINGLE_SELECTOR,
            address(usdc),
            address(usdc), // wrong tokenOut
            address(vault),
            uint256(block.timestamp + 1),
            pi[7],
            pi[8],
            uint160(0)
        );
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](1);
        trades[0] = IStrategyVault.Call({ target: allowedRouter, value: 0, data: data });
        vm.prank(operator);
        vm.expectRevert(IStrategyVault.SwapTokenOutMismatch.selector);
        vault.executeWithProof(_proofBytes(), pi, trades);
    }

    function test_ExecuteWithProof_RevertsOnSwapRecipientMismatch() public {
        uint256[] memory pi = _validInputs();
        bytes memory data = abi.encodeWithSelector(
            _EXACT_INPUT_SINGLE_SELECTOR,
            address(usdc),
            address(eth),
            operator, // recipient: operator instead of vault — would exfiltrate output
            uint256(block.timestamp + 1),
            pi[7],
            pi[8],
            uint160(0)
        );
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](1);
        trades[0] = IStrategyVault.Call({ target: allowedRouter, value: 0, data: data });
        vm.prank(operator);
        vm.expectRevert(IStrategyVault.SwapRecipientMismatch.selector);
        vault.executeWithProof(_proofBytes(), pi, trades);
    }

    function test_ExecuteWithProof_RevertsOnSwapAmountInMismatch() public {
        uint256[] memory pi = _validInputs();
        bytes memory data = abi.encodeWithSelector(
            _EXACT_INPUT_SINGLE_SELECTOR,
            address(usdc),
            address(eth),
            address(vault),
            uint256(block.timestamp + 1),
            pi[7] + 1, // wrong amountIn
            pi[8],
            uint160(0)
        );
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](1);
        trades[0] = IStrategyVault.Call({ target: allowedRouter, value: 0, data: data });
        vm.prank(operator);
        vm.expectRevert(IStrategyVault.SwapAmountInMismatch.selector);
        vault.executeWithProof(_proofBytes(), pi, trades);
    }

    function test_ExecuteWithProof_RevertsOnSwapMinOutMismatch() public {
        uint256[] memory pi = _validInputs();
        bytes memory data = abi.encodeWithSelector(
            _EXACT_INPUT_SINGLE_SELECTOR,
            address(usdc),
            address(eth),
            address(vault),
            uint256(block.timestamp + 1),
            pi[7],
            pi[8] - 1, // operator weakens minOut → could accept a worse swap
            uint160(0)
        );
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](1);
        trades[0] = IStrategyVault.Call({ target: allowedRouter, value: 0, data: data });
        vm.prank(operator);
        vm.expectRevert(IStrategyVault.SwapMinOutMismatch.selector);
        vault.executeWithProof(_proofBytes(), pi, trades);
    }

    function test_ExecuteWithProof_RevertsOnEmptyCalldata() public {
        // c.data shorter than a 4-byte selector — fall-through guard.
        uint256[] memory pi = _validInputs();
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](1);
        trades[0] = IStrategyVault.Call({ target: allowedRouter, value: 0, data: hex"" });
        vm.prank(operator);
        vm.expectRevert(IStrategyVault.TradeCallSelectorNotAllowed.selector);
        vault.executeWithProof(_proofBytes(), pi, trades);
    }

    function test_ExecuteYieldRotationWithProof_RevertsOnNonEmptyTrades() public {
        // YR rotation calldata isn't yet bound by a circuit (Phase-5 bridge
        // gadget). Until then, any non-empty trades[] is a binding gap.
        uint256[] memory pi = _yrInputs();
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](1);
        trades[0] = IStrategyVault.Call({ target: allowedRouter, value: 0, data: hex"deadbeef" });
        vm.prank(operator);
        vm.expectRevert(IStrategyVault.YRTradesNotSupported.selector);
        vault.executeYieldRotationWithProof(_proofBytes(), pi, trades);
    }
}
