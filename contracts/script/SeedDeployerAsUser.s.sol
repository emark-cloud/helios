// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";
import { IERC20 } from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import { MetaStrategyLib } from "../src/interfaces/IMetaStrategy.sol";

interface IMockERC20 {
    function mint(address to, uint256 amount) external;
}

interface IUserVault {
    function deposit(address asset, uint256 amount) external;
    function setMetaStrategy(MetaStrategyLib.MetaStrategy calldata meta, bytes calldata sig)
        external;
    function delegateToAllocator(address allocator, uint64 sessionTTL) external;
    function balanceOf(address user) external view returns (uint256);
}

/// @notice CXR-0c demo seed — deployer EOA plays a Helios user end-to-end
///         so Sentinel has a delegated user with capital that includes
///         cross-chain candidates in its allowed-chain set. Mirrors the
///         frontend onboarding flow (deposit → setMeta → delegate) but
///         from a forge script for headless seeding. The off-chain
///         meta-strategy POST is a separate step (Python helper).
///
///         Required env:
///           - DEPLOYER_PK        funded deployer key (mUSDC mint authority)
///         Reads from `./deployments/kite-testnet.json`:
///           - mUsdc, userVault, allocatorVault
contract SeedDeployerAsUser is Script {
    string internal constant FILE = "./deployments/kite-testnet.json";
    uint256 internal constant SEED_AMOUNT = 50e18; // 50 mUSDC
    uint64 internal constant SESSION_TTL = 30 days;

    function run() external {
        require(block.chainid == 2368, "SeedDeployerAsUser: not Kite testnet");

        uint256 pk = vm.envUint("DEPLOYER_PK");
        address deployer = vm.addr(pk);
        address mUsdc = _readAddress(".addresses.usdc");
        address userVault = _readAddress(".addresses.userVault");
        address allocatorVault = _readAddress(".addresses.allocatorVault");

        require(mUsdc != address(0), "mUsdc missing");
        require(userVault != address(0), "userVault missing");
        require(allocatorVault != address(0), "allocatorVault missing");

        // Build meta-strategy. The on-chain hash field is informational —
        // UserVault stores the struct as-is and doesn't recompute. The
        // off-chain Sentinel POST drives ranking; the hash here just
        // distinguishes this user's payload in `_metas[user]`.
        // Canonical Poseidon hashes per `frontend/src/lib/format.ts`. Empty
        // here would set the on-chain `_classAllowed` mapping to all-false,
        // so `AllocatorVault.allocateToStrategy` reverts MetaClassNotAllowed.
        bytes32[] memory classes = new bytes32[](3);
        classes[0] = 0x2a9aa442064b635baec37a7a259282faa5563a653a8325378d5676c6f04bc9dd; // momentum_v1
        classes[1] = 0x18602f4f74172d545f5258541634e1a125c3a4e1227ee2a4cbee957d3490f1fb; // mean_reversion_v1
        classes[2] = 0x2e882135c6afc3bda02a9c8a7c6a351198d97599c804a2575a3d616073a87251; // yield_rotation_v1
        address[] memory assets = new address[](1);
        assets[0] = mUsdc;
        uint32[] memory chains = new uint32[](3);
        chains[0] = 2368; // Kite testnet
        chains[1] = 84_532; // Base Sepolia
        chains[2] = 421_614; // Arbitrum Sepolia

        MetaStrategyLib.MetaStrategy memory meta = MetaStrategyLib.MetaStrategy({
            metaStrategyHash: keccak256(abi.encodePacked("helios.demo.deployer-as-user.v1")),
            allowedStrategyClasses: classes,
            allowedAssets: assets,
            allowedChains: chains,
            maxCapital: SEED_AMOUNT,
            maxPerStrategyBps: 2500, // 25% per strategy
            maxStrategiesCount: 8,
            drawdownThresholdBps: 2000, // 20% drawdown trigger
            maxFeeRateBps: 5000, // accept up to 50% fee
            rebalanceCadenceSec: 300,
            validUntil: uint64(block.timestamp + 30 days),
            defundTwapBars: 3,
            defundBondBps: 50,
            defundConfirmBlocks: 25
        });

        vm.startBroadcast(pk);
        IMockERC20(mUsdc).mint(deployer, SEED_AMOUNT);
        IERC20(mUsdc).approve(userVault, SEED_AMOUNT);
        IUserVault(userVault).deposit(mUsdc, SEED_AMOUNT);
        IUserVault(userVault).setMetaStrategy(meta, "");
        IUserVault(userVault).delegateToAllocator(allocatorVault, SESSION_TTL);
        vm.stopBroadcast();

        console2.log("=== CXR-0c seed: deployer-as-user ===");
        console2.log("deployer:           ", deployer);
        console2.log("UserVault balance:  ", IUserVault(userVault).balanceOf(deployer));
        console2.log("allocator:          ", allocatorVault);
        console2.log("validUntil:         ", meta.validUntil);
    }

    function _readAddress(string memory key) internal view returns (address) {
        string memory json = vm.readFile(FILE);
        bytes memory raw = vm.parseJson(json, key);
        if (raw.length == 0) return address(0);
        return abi.decode(raw, (address));
    }
}
