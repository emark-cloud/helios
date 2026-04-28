// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Test } from "forge-std/Test.sol";
import { StrategyVault } from "../src/StrategyVault.sol";
import { IStrategyVault } from "../src/interfaces/IStrategyVault.sol";
import { TradeAttestationVerifier } from "../src/TradeAttestationVerifier.sol";
import { ITradeAttestationVerifier } from "../src/interfaces/ITradeAttestationVerifier.sol";
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
    address internal navOracle;
    uint256 internal navOracleKey;
    address internal randomCaller = makeAddr("rando");

    bytes32 internal constant CLASS = keccak256("momentum_v1");
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
        bytes memory initData = abi.encodeCall(
            StrategyVault.initialize,
            (m, usdc, registry, address(verifier), allowedRouter, navOracle, allocatorVault, owner)
        );
        vault = StrategyVault(address(new ERC1967Proxy(address(impl), initData)));

        // Fund allocator vault and approve the strategy vault.
        usdc.mint(allocatorVault, 1_000_000e6);
        vm.prank(allocatorVault);
        usdc.approve(address(vault), type(uint256).max);
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
        bytes memory initData = abi.encodeCall(
            StrategyVault.initialize,
            (m, usdc, registry, address(verifier), allowedRouter, navOracle, allocatorVault, owner)
        );
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
        vm.expectRevert(Initializable.InvalidInitialization.selector);
        vault.initialize(
            m, usdc, registry, address(verifier), allowedRouter, navOracle, allocatorVault, owner
        );
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
        vm.expectRevert(Initializable.InvalidInitialization.selector);
        impl.initialize(
            m, usdc, registry, address(verifier), allowedRouter, navOracle, allocatorVault, owner
        );
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
        bytes32 digest = keccak256(abi.encode(block.chainid, address(vault), nav, ts));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(navOracleKey, digest);
        bytes memory sig = abi.encodePacked(r, s, v);
        vault.reportNAV(abi.encode(nav, ts, sig));
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
        vm.expectRevert(StrategyVault.StaleNav.selector);
        _reportNAV(1500e6, ts);
    }

    function test_ReportNAV_RevertsOnBadSigner() public {
        uint64 ts = uint64(block.timestamp + 1);
        (, uint256 wrongKey) = makeAddrAndKey("wrongOracle");
        bytes32 digest = keccak256(abi.encode(block.chainid, address(vault), uint256(1000e6), ts));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(wrongKey, digest);
        bytes memory sig = abi.encodePacked(r, s, v);
        vm.expectRevert(StrategyVault.NavSignatureInvalid.selector);
        vault.reportNAV(abi.encode(uint256(1000e6), ts, sig));
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
}
