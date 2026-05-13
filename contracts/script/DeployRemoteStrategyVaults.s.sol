// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";
import { ERC1967Proxy } from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";

import { StrategyRegistry } from "../src/StrategyRegistry.sol";
import { StrategyVault } from "../src/StrategyVault.sol";
import { IStrategyVault } from "../src/interfaces/IStrategyVault.sol";
import { MockERC20 } from "../test/mocks/MockERC20.sol";
import { ClassIds } from "../src/ClassIds.sol";
import { IERC20 } from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import { IERC20Metadata } from "@openzeppelin/contracts/token/ERC20/extensions/IERC20Metadata.sol";

/// @notice CXR-2 / CXR-3 — Deploy strategy vaults on a remote execution
///         chain so §12.1's per-chain venue routing is delivered:
///
///         - Arb-Sepolia (421614): `yr.arb` against Aave V3 Pool
///         - Base-Sepolia (84532): `mom.base` + `mr.base` against
///           Uniswap V3 SwapRouter02
///
///         Each remote chain has its own StrategyRegistry (CXR-1) — the
///         vault binds to the local SR for `paramsHashOf` and
///         `isActiveStrategy`. Reputation propagates back to Kite via the
///         existing HeliosOApp pipe; allocator capital lands via the
///         BridgeReceiver hooks added in CXR-0b. Until CXR-0b's bridge
///         receiver is wired with `setBridgeReceiver(...)`, the vault has
///         no inbound allocate path — operator-driven `executeWithProof`
///         still works once the strategy operator funds the vault
///         directly for the bring-up smoke test.
///
///         `allocatorVault` is set to the deployer as a placeholder. The
///         PI_ALLOCATOR check in the verifier binds the witness to this
///         slot — strategy operators on remote chains must use the
///         deployer address in their public-input witness construction.
///         The bridge-receiver gate (`bridgeReceiver`) is a separate
///         slot, set post-deploy via `setBridgeReceiver(...)`.
///
///         Required env:
///           - DEPLOYER_PK     funded testnet key
///           - REMOTE_CHAIN    "arb" | "base"
///           - STRATEGY_VAULT_IMPL (optional) — reuse the existing impl
///             at `0x78b3515f...`; deploys a fresh impl on dry-run forks.
///
///         Reads from `./deployments/{chain}-sepolia.json`:
///           - usdc, strategyRegistry, tradeAttestationVerifier
///           - oraclePriceAnchor, oracleYieldAnchor
///           - aavePool (Arb) or swapRouter (Base placeholder)
///
///         Patches under `addresses.`:
///           - Arb:  phase6VaultYieldRotationArb
///           - Base: phase6VaultMomentumBase, phase6VaultMeanReversionBase
contract DeployRemoteStrategyVaults is Script {
    bytes32 internal constant CLASS_MOM = ClassIds.MOMENTUM_V1;
    bytes32 internal constant CLASS_MR = ClassIds.MEAN_REVERSION_V1;
    bytes32 internal constant CLASS_YR = ClassIds.YIELD_ROTATION_V1;

    uint16 internal constant STRATEGY_FEE_BPS = 1500;
    /// @dev Whole-token amounts; scaled to baseAsset.decimals() at deploy
    ///      time. Kite mUSDC is 18-dec; Arb-Sepolia mUSDC is 6-dec, so
    ///      hard-coded 18-dec literals would mis-size the vault by 1e12x.
    uint256 internal constant STAKE_WHOLE = 5_000;
    uint256 internal constant CAPACITY_WHOLE = 1_000_000;

    bytes32 internal constant PH_YR_ARB =
        keccak256("helios.yield_rot_v1.phase6.multiasset.arb");
    bytes32 internal constant PH_MOM_BASE_REMOTE =
        keccak256("helios.mom_v1.phase6.multiasset.base.remote");
    bytes32 internal constant PH_MR_BASE_REMOTE =
        keccak256("helios.mean_rev_v1.phase6.multiasset.base.remote");

    struct Inputs {
        uint256 deployerPk;
        address deployer;
        address impl;
        address usdc;
        address registry;
        address verifier;
        address router;
        address priceAnchor;
        address yieldAnchor;
        string file;
    }

    function run() external {
        Inputs memory i = _loadInputs();

        vm.startBroadcast(i.deployerPk);

        if (i.impl == address(0)) {
            StrategyVault impl = new StrategyVault(i.priceAnchor, i.yieldAnchor);
            i.impl = address(impl);
            console2.log("StrategyVault impl (fresh):", i.impl);
        } else {
            console2.log("StrategyVault impl (reused):", i.impl);
        }

        if (block.chainid == 421614) {
            _deployArbitrum(i);
        } else if (block.chainid == 84532) {
            _deployBase(i);
        } else {
            revert("DeployRemoteStrategyVaults: unsupported chain");
        }

        vm.stopBroadcast();
    }

    function _loadInputs() internal view returns (Inputs memory i) {
        i.deployerPk = vm.envUint("DEPLOYER_PK");
        i.deployer = vm.addr(i.deployerPk);
        i.impl = vm.envOr("STRATEGY_VAULT_IMPL", address(0));

        if (block.chainid == 421614) {
            i.file = "./deployments/arbitrum-sepolia.json";
        } else if (block.chainid == 84532) {
            i.file = "./deployments/base-sepolia.json";
        } else {
            revert("unsupported chain");
        }

        i.usdc = _readAddress(i.file, ".addresses.usdc");
        i.registry = _readAddress(i.file, ".addresses.strategyRegistry");
        i.verifier = _readAddress(i.file, ".addresses.tradeAttestationVerifier");
        i.priceAnchor = _readAddress(i.file, ".addresses.oraclePriceAnchor");
        i.yieldAnchor = _readAddress(i.file, ".addresses.oracleYieldAnchor");

        require(i.usdc != address(0), "usdc missing");
        require(i.registry != address(0), "strategyRegistry missing (run CXR-1 first)");
        require(i.verifier != address(0), "tradeAttestationVerifier missing");
        require(i.priceAnchor != address(0), "oraclePriceAnchor missing");

        if (block.chainid == 421614) {
            // On Arb-Sepolia, real Aave V3's USDC/WETH reserves are
            // gated to admin-only mint (FiatToken). v1 routes yr.arb
            // through the Helios-deployed MockYieldVault `0xc065af9b…`
            // — same Aave-V3-shaped supply/withdraw interface, real
            // remote-chain execution. Real Aave swap is a one-line
            // env flip once an Aave faucet is accessible.
            i.router = _readAddress(i.file, ".addresses.mockYieldVault");
            require(i.router != address(0), "mockYieldVault missing on Arb");
            require(i.yieldAnchor != address(0), "oracleYieldAnchor missing on Arb");
        } else {
            // On Base, prefer an explicit `uniswapV3Router` if present in
            // the JSON; otherwise fall back to env. On Base-Sepolia the
            // SwapRouter02 lives at 0x94cc0aac...
            i.router = _readAddress(i.file, ".addresses.uniswapV3Router");
            if (i.router == address(0)) {
                i.router = vm.envAddress("UNISWAP_V3_ROUTER");
            }
            require(i.router != address(0), "uniswapV3Router missing on Base");
            // Yield anchor is not required on Base (mom/mr only).
            if (i.yieldAnchor == address(0)) {
                i.yieldAnchor = i.priceAnchor; // benign — only read on YR path
            }
        }
    }

    function _deployArbitrum(Inputs memory i) internal {
        address[] memory universe = new address[](1);
        universe[0] = i.usdc;

        address vault =
            _deployOne(i, CLASS_YR, universe, PH_YR_ARB, "yr.arb");

        // Approve + register on local SR. Stake scaled to baseAsset decimals.
        uint256 stake = _stake(i.usdc);
        IERC20(i.usdc).approve(i.registry, type(uint256).max);
        StrategyRegistry(i.registry).registerStrategy(vault, CLASS_YR, stake);
        console2.log("registered yr.arb on local SR (stake)", stake);

        vm.writeJson(
            string.concat('"', vm.toString(vault), '"'),
            i.file,
            ".addresses.phase6VaultYieldRotationArb"
        );
        vm.writeJson(
            string.concat('"', vm.toString(i.impl), '"'),
            i.file,
            ".addresses.strategyVaultImpl"
        );
        console2.log("patched:", i.file);
    }

    function _deployBase(Inputs memory i) internal {
        address[] memory universe = new address[](2);
        universe[0] = i.usdc;
        // Base-Sepolia WETH-equivalent — read from JSON; falls back to
        // env WETH if not preset. mom/mr witnesses bind to a 2-asset
        // universe at minimum; richer universes (WBTC, WSOL) can be
        // added once Base test pools exist with non-trivial depth.
        address weth = _readAddress(i.file, ".addresses.weth");
        if (weth == address(0)) {
            weth = vm.envAddress("WETH");
        }
        require(weth != address(0), "weth missing on Base");
        universe[1] = weth;

        address momVault =
            _deployOne(i, CLASS_MOM, universe, PH_MOM_BASE_REMOTE, "mom.base");
        address mrVault =
            _deployOne(i, CLASS_MR, universe, PH_MR_BASE_REMOTE, "mr.base");

        uint256 stake = _stake(i.usdc);
        IERC20(i.usdc).approve(i.registry, type(uint256).max);
        StrategyRegistry(i.registry).registerStrategy(momVault, CLASS_MOM, stake);
        StrategyRegistry(i.registry).registerStrategy(mrVault, CLASS_MR, stake);
        console2.log("registered mom.base + mr.base on local SR (stake)", stake);

        vm.writeJson(
            string.concat('"', vm.toString(momVault), '"'),
            i.file,
            ".addresses.phase6VaultMomentumBase"
        );
        vm.writeJson(
            string.concat('"', vm.toString(mrVault), '"'),
            i.file,
            ".addresses.phase6VaultMeanReversionBase"
        );
        vm.writeJson(
            string.concat('"', vm.toString(i.impl), '"'),
            i.file,
            ".addresses.strategyVaultImpl"
        );
        console2.log("patched:", i.file);
    }

    function _deployOne(
        Inputs memory i,
        bytes32 declaredClass,
        address[] memory universe,
        bytes32 paramsHash,
        string memory label
    ) internal returns (address vault) {
        uint8 dec = IERC20Metadata(i.usdc).decimals();
        uint256 stake = STAKE_WHOLE * (10 ** dec);
        uint256 capacity = CAPACITY_WHOLE * (10 ** dec);
        IStrategyVault.StrategyManifest memory m = IStrategyVault.StrategyManifest({
            declaredClass: declaredClass,
            assetUniverse: universe,
            maxCapacity: capacity,
            feeRateBps: STRATEGY_FEE_BPS,
            operator: i.deployer,
            stakeAmount: stake,
            paramsHash: paramsHash
        });

        StrategyVault.InitParams memory p = StrategyVault.InitParams({
            manifest: m,
            baseAsset: MockERC20(i.usdc),
            registry: i.registry,
            verifier: i.verifier,
            allowedRouter: i.router,
            navOracle: i.deployer,
            // Placeholder — PI_ALLOCATOR binding only; cross-chain
            // allocate path gates on the separate `bridgeReceiver` slot
            // wired post-deploy via setBridgeReceiver.
            allocatorVault: i.deployer,
            priceAnchor: i.priceAnchor,
            yieldAnchor: i.yieldAnchor,
            owner: i.deployer
        });

        vault = address(new ERC1967Proxy(i.impl, abi.encodeCall(StrategyVault.initialize, (p))));
        console2.log(string.concat("StrategyVault[", label, "]:"), vault);
    }

    function _readAddress(string memory file, string memory key) internal view returns (address) {
        string memory json = vm.readFile(file);
        bytes memory raw = vm.parseJson(json, key);
        if (raw.length == 0) return address(0);
        return abi.decode(raw, (address));
    }

    function _stake(address token) internal view returns (uint256) {
        return STAKE_WHOLE * (10 ** IERC20Metadata(token).decimals());
    }
}
