// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";
import { ERC1967Proxy } from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";

import { StrategyRegistry } from "../src/StrategyRegistry.sol";
import { StrategyVault } from "../src/StrategyVault.sol";
import { IStrategyVault } from "../src/interfaces/IStrategyVault.sol";
import { MockERC20 } from "../test/mocks/MockERC20.sol";
import { ClassIds } from "../src/ClassIds.sol";

/// @notice WS6 PR3.5.C — register a SINGLE fresh strategy mid-scenario
///         so the WS7.B bootstrap-pool path can be exercised end-to-end.
///
///         The Phase-2 e2e starts with 6 vaults (2 per class). After
///         the trade flows + reputation tick land, this script bolts
///         on a 7th vault (`strategyVaultMomentumVariant3`) with the
///         same momentum_v1 declared class but a different params hash.
///         The new vault has zero trades_attested, which is what the
///         sentinel bootstrap pool checks (`trades_attested <
///         min_attested_trades`) before allocating cold-start capital.
///
///         Inputs match RegisterPhase2Strategies.s.sol so the same
///         env wiring in scripts/e2e-scenario-phase2.sh applies.
contract RegisterFreshStrategy is Script {
    bytes32 internal constant CLASS_MOM = ClassIds.MOMENTUM_V1;

    uint16 internal constant STRATEGY_FEE_BPS = 1500;
    uint256 internal constant STRATEGY_STAKE_3 = 5000e6; // 5k USDC — matches variant1/variant2
    uint256 internal constant MAX_CAPACITY = 1_000_000e6;

    /// @dev Distinct paramsHash from variant1/variant2 so the cohort
    ///      sees three separate momentum strategies, not duplicates.
    bytes32 internal constant PARAMS_HASH_MOM_V3 =
        keccak256("helios.mom_v1.variant3.fresh-bootstrap");

    struct Inputs {
        uint256 deployerPk;
        address usdc;
        address strategyRegistry;
        address allocatorVault;
        address tradeVerifier;
        address swapRouter;
        string outLabel;
    }

    function run() external returns (address freshVault) {
        uint256 pk = vm.envUint("DEPLOYER_PK");
        Inputs memory i = Inputs({
            deployerPk: pk,
            usdc: vm.envAddress("USDC"),
            strategyRegistry: vm.envAddress("STRATEGY_REGISTRY"),
            allocatorVault: vm.envAddress("ALLOCATOR_VAULT"),
            tradeVerifier: vm.envAddress("TRADE_VERIFIER"),
            swapRouter: vm.envAddress("SWAP_ROUTER"),
            outLabel: vm.envOr("OUT_LABEL", _chainName())
        });
        return runWith(i);
    }

    function runWith(Inputs memory i) public returns (address freshVault) {
        address deployer = vm.addr(i.deployerPk);

        vm.startBroadcast(i.deployerPk);
        freshVault = _deployFresh(i, deployer);

        // Top up USDC approval; runs after the variant2 register pass
        // which set type(uint256).max — defensive in case a different
        // operator broadcasts.
        MockERC20(i.usdc).approve(i.strategyRegistry, type(uint256).max);
        StrategyRegistry(i.strategyRegistry)
            .registerStrategy(freshVault, CLASS_MOM, STRATEGY_STAKE_3);
        vm.stopBroadcast();

        _logAndPersist(freshVault, i.outLabel);
    }

    function _deployFresh(Inputs memory i, address deployer) internal returns (address) {
        StrategyVault impl = new StrategyVault();
        address[] memory universe = new address[](1);
        universe[0] = i.usdc;
        IStrategyVault.StrategyManifest memory m = IStrategyVault.StrategyManifest({
            declaredClass: CLASS_MOM,
            assetUniverse: universe,
            maxCapacity: MAX_CAPACITY,
            feeRateBps: STRATEGY_FEE_BPS,
            operator: deployer,
            stakeAmount: STRATEGY_STAKE_3,
            paramsHash: PARAMS_HASH_MOM_V3
        });
        bytes memory init = abi.encodeCall(
            StrategyVault.initialize,
            (
                m,
                MockERC20(i.usdc),
                i.strategyRegistry,
                i.tradeVerifier,
                i.swapRouter,
                deployer,
                i.allocatorVault,
                deployer
            )
        );
        address vault = address(new ERC1967Proxy(address(impl), init));
        console2.log("StrategyVault[momentum_v1.variant3]:", vault);
        return vault;
    }

    function _logAndPersist(address freshVault, string memory label) internal {
        console2.log("=== Helios WS6 PR3.5.C fresh strategy registered ===");
        console2.log("StrategyVault[mom.v3]: ", freshVault);

        string memory file = string.concat("./deployments/", label, ".json");
        _patchJson(file, freshVault);
        console2.log("merged into:", file);
    }

    /// @dev Same merge strategy as DeployPhase2 / RegisterPhase2Strategies
    ///      — read existing addresses, copy every key forward, append
    ///      `strategyVaultMomentumVariant3`. Top-level metadata
    ///      preserved; stamps `phase2CFreshDeployedAt`.
    function _patchJson(string memory file, address freshVault) internal {
        string memory raw = vm.readFile(file);
        uint256 chainIdVal = vm.parseJsonUint(raw, ".chainId");
        uint256 deployedAtVal = vm.parseJsonUint(raw, ".deployedAt");

        string memory addrsBody = _existingAddresses(raw);
        addrsBody = string.concat(addrsBody, _kvLast("strategyVaultMomentumVariant3", freshVault));

        string memory merged = string.concat(
            "{\n",
            '  "chainId": ',
            vm.toString(chainIdVal),
            ",\n",
            '  "deployedAt": ',
            vm.toString(deployedAtVal),
            ',\n  "phase": "2",\n',
            '  "phase2CFreshDeployedAt": ',
            vm.toString(block.timestamp),
            ',\n  "addresses": {\n',
            addrsBody,
            "  }\n}\n"
        );
        vm.writeFile(file, merged);
    }

    function _existingAddresses(string memory raw) internal pure returns (string memory body) {
        string[] memory keys = vm.parseJsonKeys(raw, ".addresses");
        bytes32 freshKey = keccak256("strategyVaultMomentumVariant3");
        for (uint256 i = 0; i < keys.length; i++) {
            string memory k = keys[i];
            if (keccak256(bytes(k)) == freshKey) continue; // dedupe on re-run
            address val = vm.parseJsonAddress(raw, string.concat(".addresses.", k));
            body = string.concat(body, _kv(k, val));
        }
    }

    function _kv(string memory k, address v) internal pure returns (string memory) {
        return string.concat('    "', k, '": "', _addrLower(v), '",\n');
    }

    function _kvLast(string memory k, address v) internal pure returns (string memory) {
        return string.concat('    "', k, '": "', _addrLower(v), '"\n');
    }

    function _addrLower(address v) internal pure returns (string memory) {
        bytes memory hexChars = "0123456789abcdef";
        bytes20 b = bytes20(v);
        bytes memory out = new bytes(42);
        out[0] = "0";
        out[1] = "x";
        for (uint256 i = 0; i < 20; i++) {
            out[2 + i * 2] = hexChars[uint8(b[i] >> 4)];
            out[3 + i * 2] = hexChars[uint8(b[i] & 0x0f)];
        }
        return string(out);
    }

    function _chainName() internal view returns (string memory) {
        if (block.chainid == 2368) return "kite-testnet";
        if (block.chainid == 84_532) return "base-sepolia";
        if (block.chainid == 421_614) return "arbitrum-sepolia";
        if (block.chainid == 31_337) return "anvil";
        return vm.toString(block.chainid);
    }
}
