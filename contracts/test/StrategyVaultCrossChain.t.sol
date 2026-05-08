// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Test } from "forge-std/Test.sol";
import { ClassIds } from "../src/ClassIds.sol";
import { StrategyVault } from "../src/StrategyVault.sol";
import { IStrategyVault } from "../src/interfaces/IStrategyVault.sol";
import { TradeAttestationVerifier } from "../src/TradeAttestationVerifier.sol";
import { IStrategyRegistry } from "../src/interfaces/IStrategyRegistry.sol";
import { IOracleAnchor } from "../src/interfaces/IOracleAnchor.sol";
import { IHeliosOApp } from "../src/interfaces/IHeliosOApp.sol";
import { IReputationAnchor } from "../src/interfaces/IReputationAnchor.sol";
import { MockERC20 } from "./mocks/MockERC20.sol";
import { MockGroth16Verifier } from "./mocks/MockGroth16Verifier.sol";
import { ERC1967Proxy } from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";
import { Ownable } from "@openzeppelin/contracts/access/Ownable.sol";

/// @notice Phase-5 WS5 — verifies the StrategyVault cross-chain
///         attestation forwarder. Mirrors the canonical test setup
///         from `StrategyVault.t.sol` so the hook can be exercised
///         against a fully-initialised vault, then drives the
///         post-verify path with a recording mock OApp.
contract StrategyVaultCrossChainTest is Test {
    StrategyVault internal impl;
    StrategyVault internal vault;
    TradeAttestationVerifier internal verifier;
    MockGroth16Verifier internal classVerifier;
    MockERC20 internal usdc;
    MockERC20 internal eth;
    RecordingHeliosOApp internal oApp;

    address internal owner = makeAddr("owner");
    address internal operator = makeAddr("operator");
    address internal allocatorVault = makeAddr("allocatorVault");
    address internal registry = makeAddr("registry");
    address internal allowedRouter = makeAddr("router");
    address internal priceAnchor = makeAddr("priceAnchor");
    address internal yieldAnchor = makeAddr("yieldAnchor");
    address internal navOracle = makeAddr("navOracle");

    uint256 internal constant BASE_SEPOLIA_CHAIN_ID = 84_532;
    uint256 internal constant KITE_TESTNET_CHAIN_ID = 2368;

    bytes32 internal constant CLASS = ClassIds.MOMENTUM_V1;

    event HeliosOAppUpdated(address indexed previous, address indexed current);
    event CrossChainAttestationQueued(
        address indexed strategy, address indexed oApp, bytes32 indexed tradeHash
    );

    function setUp() public {
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
            maxCapacity: 1_000_000e18,
            feeRateBps: 1000,
            operator: operator,
            stakeAmount: 5000e18,
            paramsHash: bytes32(uint256(0xfee5))
        });

        impl = new StrategyVault(priceAnchor, yieldAnchor);
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
        vault = StrategyVault(
            address(new ERC1967Proxy(address(impl), abi.encodeCall(StrategyVault.initialize, (p))))
        );

        oApp = new RecordingHeliosOApp();

        // Mirror the canonical mocks the parent test ships so the
        // proof-binding gates pass without any chain-specific deploy.
        vm.mockCall(
            registry,
            abi.encodeWithSelector(IStrategyRegistry.paramsHashOf.selector),
            abi.encode(bytes32(uint256(0xfee5)))
        );
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
    }

    // ── setHeliosOApp ─────────────────────────────────────────────

    function test_SetHeliosOApp_OnlyOwner() public {
        vm.prank(makeAddr("rando"));
        vm.expectRevert(
            abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, makeAddr("rando"))
        );
        vault.setHeliosOApp(address(oApp));
    }

    function test_SetHeliosOApp_EmitsAndUpdates() public {
        vm.expectEmit(true, true, false, false);
        emit HeliosOAppUpdated(address(0), address(oApp));
        vm.prank(owner);
        vault.setHeliosOApp(address(oApp));
        assertEq(vault.heliosOApp(), address(oApp));
    }

    function test_SetHeliosOApp_CanClearByZero() public {
        vm.prank(owner);
        vault.setHeliosOApp(address(oApp));
        vm.prank(owner);
        vault.setHeliosOApp(address(0));
        assertEq(vault.heliosOApp(), address(0));
    }

    // ── Hook activation ───────────────────────────────────────────

    function test_HookIsNoOp_OnKite_EvenWithOAppSet() public {
        vm.chainId(KITE_TESTNET_CHAIN_ID);
        vm.prank(owner);
        vault.setHeliosOApp(address(oApp));

        uint256[] memory pi = _validInputs();
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](0);
        vm.prank(operator);
        vault.executeWithProof(_proofBytes(), pi, trades);

        assertEq(oApp.queueCount(), 0, "Kite vault must not forward attestations");
    }

    function test_HookIsNoOp_WhenOAppUnset_OnRemoteChain() public {
        vm.chainId(BASE_SEPOLIA_CHAIN_ID);
        // heliosOApp left at zero on purpose.

        uint256[] memory pi = _validInputs();
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](0);
        vm.prank(operator);
        vault.executeWithProof(_proofBytes(), pi, trades);

        assertEq(oApp.queueCount(), 0);
    }

    function test_HookForwards_OnRemoteChain_WhenOAppSet() public {
        vm.chainId(BASE_SEPOLIA_CHAIN_ID);
        vm.prank(owner);
        vault.setHeliosOApp(address(oApp));

        uint256[] memory pi = _validInputs();
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](0);

        vm.expectEmit(true, true, true, false);
        emit CrossChainAttestationQueued(address(vault), address(oApp), bytes32(pi[0]));
        vm.prank(operator);
        vault.executeWithProof(_proofBytes(), pi, trades);

        assertEq(oApp.queueCount(), 1);
        (address strategy, IReputationAnchor.ReputationData memory data) = oApp.queuedAt(0);
        assertEq(strategy, address(vault));
        assertEq(data.totalAttestedTrades, 1);
        assertEq(data.proofValidityRateBps, 10_000);
        assertEq(data.lastUpdateBlock, block.number);
        assertEq(uint256(data.actorType), uint256(IReputationAnchor.ActorType.STRATEGY));
        assertEq(data.componentsHash, bytes32(pi[0]));
    }

    function test_HookPropagatesQueueRevert_WhenOAppRejects() public {
        vm.chainId(BASE_SEPOLIA_CHAIN_ID);
        vm.prank(owner);
        vault.setHeliosOApp(address(oApp));

        oApp.setShouldRevert(true);

        uint256[] memory pi = _validInputs();
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](0);
        vm.prank(operator);
        vm.expectRevert(bytes("oapp: rejected"));
        vault.executeWithProof(_proofBytes(), pi, trades);

        assertEq(oApp.queueCount(), 0);
    }

    function test_HookForwards_OnArbitrumChainId() public {
        vm.chainId(421_614);
        vm.prank(owner);
        vault.setHeliosOApp(address(oApp));

        uint256[] memory pi = _validInputs();
        IStrategyVault.Call[] memory trades = new IStrategyVault.Call[](0);
        vm.prank(operator);
        vault.executeWithProof(_proofBytes(), pi, trades);

        assertEq(oApp.queueCount(), 1);
    }

    // ── Helpers ───────────────────────────────────────────────────

    function _proofBytes() internal pure returns (bytes memory) {
        uint256[2] memory a = [uint256(1), 2];
        uint256[2][2] memory b = [[uint256(3), 4], [uint256(5), 6]];
        uint256[2] memory c = [uint256(7), 8];
        return abi.encode(a, b, c);
    }

    function _validInputs() internal view returns (uint256[] memory pi) {
        pi = new uint256[](14);
        pi[0] = uint256(keccak256("trade-cx-1"));
        pi[1] = uint256(CLASS);
        pi[2] = uint256(uint160(address(vault)));
        pi[3] = uint256(bytes32(uint256(0xfee5)));
        pi[4] = uint256(uint160(allocatorVault));
        pi[5] = 0;
        pi[6] = 1;
        pi[7] = 100e6;
        pi[8] = 1e16;
        pi[9] = 1;
        pi[10] = 1;
        pi[11] = block.number;
        pi[12] = block.number + 10;
        pi[13] = uint256(keccak256("oracle-root-cx-1"));
    }
}

/// @dev Minimal IHeliosOApp stub: records queued attestations + can
///      flip a switch to revert, so the StrategyVault hook is
///      exercised without dragging the LayerZero-V2 lib into the test.
contract RecordingHeliosOApp {
    struct QueuedEntry {
        address strategy;
        IReputationAnchor.ReputationData data;
    }

    QueuedEntry[] internal _queued;
    bool public shouldRevert;

    function setShouldRevert(bool v) external {
        shouldRevert = v;
    }

    function queueAttestation(address strategy, IReputationAnchor.ReputationData calldata data)
        external
    {
        if (shouldRevert) revert("oapp: rejected");
        _queued.push(QueuedEntry({ strategy: strategy, data: data }));
    }

    function queueCount() external view returns (uint256) {
        return _queued.length;
    }

    function queuedAt(uint256 i)
        external
        view
        returns (address strategy, IReputationAnchor.ReputationData memory data)
    {
        QueuedEntry memory entry = _queued[i];
        return (entry.strategy, entry.data);
    }
}
