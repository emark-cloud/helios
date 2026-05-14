// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";
import { MetaStrategyLib } from "../src/interfaces/IMetaStrategy.sol";

interface IUserVault {
    function setMetaStrategy(MetaStrategyLib.MetaStrategy calldata meta, bytes calldata sig)
        external;
}

/// @notice Re-call `UserVault.setMetaStrategy` for the deployer (CXR-0c
///         demo seed) populating `allowedStrategyClasses` with the three
///         canonical Poseidon class hashes. Idempotent: just rewrites
///         meta. Safe because `userTotalDeployed == 0` (no positions
///         yet) — the HIGH #5 tightening guard never trips.
contract UpdateUserMetaClasses is Script {
    string internal constant FILE = "./deployments/kite-testnet.json";

    function run() external {
        require(block.chainid == 2_368, "not Kite testnet");
        uint256 pk = vm.envUint("DEPLOYER_PK");
        address mUsdc = _readAddress(".addresses.usdc");
        address userVault = _readAddress(".addresses.userVault");

        bytes32[] memory classes = new bytes32[](3);
        classes[0] = 0x2a9aa442064b635baec37a7a259282faa5563a653a8325378d5676c6f04bc9dd;
        classes[1] = 0x18602f4f74172d545f5258541634e1a125c3a4e1227ee2a4cbee957d3490f1fb;
        classes[2] = 0x2e882135c6afc3bda02a9c8a7c6a351198d97599c804a2575a3d616073a87251;

        address[] memory assets = new address[](1);
        assets[0] = mUsdc;

        uint32[] memory chains = new uint32[](3);
        chains[0] = 2_368;
        chains[1] = 84_532;
        chains[2] = 421_614;

        MetaStrategyLib.MetaStrategy memory meta = MetaStrategyLib.MetaStrategy({
            metaStrategyHash: keccak256(abi.encodePacked("helios.demo.deployer-as-user.v2")),
            allowedStrategyClasses: classes,
            allowedAssets: assets,
            allowedChains: chains,
            maxCapital: 50e18,
            maxPerStrategyBps: 2_500,
            maxStrategiesCount: 8,
            drawdownThresholdBps: 2_000,
            maxFeeRateBps: 5_000,
            rebalanceCadenceSec: 300,
            validUntil: uint64(block.timestamp + 30 days),
            defundTwapBars: 3,
            defundBondBps: 50,
            defundConfirmBlocks: 25
        });

        vm.startBroadcast(pk);
        IUserVault(userVault).setMetaStrategy(meta, "");
        vm.stopBroadcast();

        console2.log("=== UpdateUserMetaClasses ===");
        console2.log("deployer:", vm.addr(pk));
        console2.log("classes[]:", classes.length);
    }

    function _readAddress(string memory key) internal view returns (address) {
        string memory json = vm.readFile(FILE);
        bytes memory raw = vm.parseJson(json, key);
        if (raw.length == 0) return address(0);
        return abi.decode(raw, (address));
    }
}
