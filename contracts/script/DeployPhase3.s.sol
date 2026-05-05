// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Script, console2 } from "forge-std/Script.sol";
import { ERC1967Proxy } from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";
import { IERC20 } from "@openzeppelin/contracts/token/ERC20/IERC20.sol";

import { AllocatorRegistry } from "../src/AllocatorRegistry.sol";
import { AllocatorVault } from "../src/AllocatorVault.sol";
import { ClassIds } from "../src/ClassIds.sol";

/// @notice Phase-3 — Helios Helix on-chain registration. Reads Phase-1/2
///         infrastructure addresses from `deployments/<chain>.json`, then
///         deploys a second `AllocatorVault` proxy for Helix and registers
///         it under the shadow name `"Helios Helix-shadow"` on the existing
///         `AllocatorRegistry`. Mirrors the Phase-1 Sentinel pattern: the
///         multi-sig flips to the reserved name + sets `isReferenceBrand`
///         in a follow-up tx via `assignReferenceBrand` so testnet ops can
///         rotate operator keys without touching the brand.
///
///         Required env (`run()`):
///           - DEPLOYER_PK
///         Optional env:
///           - HELIX_OPERATOR  (default: deployer; allocator service signer)
///           - HELIX_FEE_BPS   (default: 600 — `Helios.md §11.4` callout)
///           - HELIX_STAKE     (default: 5000e6 USDC, mirrors Sentinel)
///           - OUT_LABEL       (default: chain name)
///
///         Backwards compat: only mutates `AllocatorRegistry` via a
///         standard `registerAllocator` call. No vault upgrades, no class
///         map changes, no reputation anchor cutover. Safe to re-run on
///         testnet — the second invocation reverts on
///         `AllocatorAlreadyRegistered` because the helix vault address is
///         deterministic via CREATE only when nothing else mints between
///         broadcasts; in practice we just rotate `HELIX_OPERATOR` and
///         redeploy a fresh vault.
contract DeployPhase3 is Script {
    bytes32 internal constant CLASS_MOM = ClassIds.MOMENTUM_V1;
    bytes32 internal constant CLASS_MR = ClassIds.MEAN_REVERSION_V1;
    bytes32 internal constant CLASS_YR = ClassIds.YIELD_ROTATION_V1;

    uint16 internal constant HELIX_FEE_BPS_DEFAULT = 600;
    uint256 internal constant HELIX_STAKE_DEFAULT = 5000e6;

    /// @notice Inputs for the parameterised entry point. Production deploys
    ///         use `run()` which reads these from env + the deployments
    ///         JSON; tests instantiate the struct directly via `runWith`.
    struct Inputs {
        uint256 deployerPk;
        address allocatorRegistry;
        address userVault;
        address strategyRegistry;
        IERC20 stakeToken;
        address helixOperator;
        uint16 feeRateBps;
        uint256 stakeAmount;
        string outLabel;
    }

    struct Phase3Addresses {
        address helixAllocatorVault;
        address helixAllocatorId;
    }

    function run() external returns (Phase3Addresses memory a) {
        uint256 pk = vm.envUint("DEPLOYER_PK");
        address deployer = vm.addr(pk);
        string memory label = vm.envOr("OUT_LABEL", _chainName());
        string memory file = string.concat("./deployments/", label, ".json");
        string memory raw = vm.readFile(file);

        Inputs memory i = Inputs({
            deployerPk: pk,
            allocatorRegistry: vm.parseJsonAddress(raw, ".addresses.allocatorRegistry"),
            userVault: vm.parseJsonAddress(raw, ".addresses.userVault"),
            strategyRegistry: vm.parseJsonAddress(raw, ".addresses.strategyRegistry"),
            stakeToken: IERC20(vm.parseJsonAddress(raw, ".addresses.usdc")),
            helixOperator: vm.envOr("HELIX_OPERATOR", deployer),
            feeRateBps: uint16(vm.envOr("HELIX_FEE_BPS", uint256(HELIX_FEE_BPS_DEFAULT))),
            stakeAmount: vm.envOr("HELIX_STAKE", HELIX_STAKE_DEFAULT),
            outLabel: label
        });
        return runWith(i);
    }

    function runWith(Inputs memory i) public returns (Phase3Addresses memory a) {
        address deployer = vm.addr(i.deployerPk);

        vm.startBroadcast(i.deployerPk);
        a.helixAllocatorVault = _deployHelixVault(i, deployer);
        a.helixAllocatorId = _registerHelix(i, a.helixAllocatorVault);
        vm.stopBroadcast();

        _logAndPersist(a, i.outLabel);
    }

    function _deployHelixVault(Inputs memory i, address deployer) internal returns (address) {
        AllocatorVault impl = new AllocatorVault();
        bytes memory init = abi.encodeCall(
            AllocatorVault.initialize,
            (i.stakeToken, i.helixOperator, i.userVault, i.strategyRegistry, i.feeRateBps, deployer)
        );
        return address(new ERC1967Proxy(address(impl), init));
    }

    function _registerHelix(Inputs memory i, address helixVault) internal returns (address) {
        bytes32[] memory supported = new bytes32[](3);
        supported[0] = CLASS_MOM;
        supported[1] = CLASS_MR;
        supported[2] = CLASS_YR;
        i.stakeToken.approve(i.allocatorRegistry, type(uint256).max);
        // Registered under the shadow name. Phase-3 deploy does not call
        // `assignReferenceBrand` — a multi-sig follow-up tx reserves
        // "Helios Helix-shadow" (or rotates the entry name via redeploy)
        // and sets the brand flag. See `Helios.md §6.6`.
        return AllocatorRegistry(i.allocatorRegistry)
            .registerAllocator(
                "Helios Helix-shadow",
                helixVault,
                keccak256("helix_v1_ranking"),
                supported,
                i.feeRateBps,
                i.stakeAmount
            );
    }

    // ── Logging + JSON persistence ─────────────────────────────────

    function _logAndPersist(Phase3Addresses memory a, string memory label) internal {
        _logAddresses(a);
        string memory file = string.concat("./deployments/", label, ".json");
        _patchJson(file, a);
        console2.log("merged into:", file);
    }

    /// @dev Merges Phase-3 addresses into `deployments/<label>.json`. The
    ///      existing file is read, every key under `.addresses` is copied
    ///      forward (skipping the helix slots that this run owns), then
    ///      the new helix keys are appended. `.phase` bumps to "3";
    ///      `.phase3DeployedAt` is stamped; non-standard top-level keys
    ///      (`.phase2DeployedAt`, `.phase2BVariant3DeployedAt`, etc.) are
    ///      preserved as opaque uint timestamps.
    function _patchJson(string memory file, Phase3Addresses memory a) internal {
        string memory raw = vm.readFile(file);
        uint256 chainIdVal = vm.parseJsonUint(raw, ".chainId");
        uint256 deployedAtVal = vm.parseJsonUint(raw, ".deployedAt");

        string memory addrsBody = _carriedForwardAddresses(raw);
        addrsBody = string.concat(addrsBody, _phase3Addresses(a));

        string memory merged = string.concat(
            "{\n",
            '  "chainId": ',
            vm.toString(chainIdVal),
            ",\n",
            '  "deployedAt": ',
            vm.toString(deployedAtVal),
            ',\n  "phase": "3",\n',
            _carriedForwardTopLevelStamps(raw),
            '  "phase3DeployedAt": ',
            vm.toString(block.timestamp),
            ',\n  "addresses": {\n',
            addrsBody,
            "  }\n}\n"
        );
        vm.writeFile(file, merged);
    }

    /// @dev Copy every existing `.addresses.*` key forward, skipping the
    ///      slots Phase-3 owns. Re-running the script over the same file
    ///      then writes a single fresh helix block instead of duplicating.
    function _carriedForwardAddresses(string memory raw)
        internal
        pure
        returns (string memory body)
    {
        string[] memory keys = vm.parseJsonKeys(raw, ".addresses");
        for (uint256 i = 0; i < keys.length; i++) {
            string memory k = keys[i];
            if (_isPhase3OverrideKey(k)) continue;
            address v = vm.parseJsonAddress(raw, string.concat(".addresses.", k));
            body = string.concat(body, _kv(k, v));
        }
    }

    /// @dev Preserve any top-level uint timestamp keys outside the
    ///      well-known set. Phase-2 adds `phase2DeployedAt` /
    ///      `phase2BVariant3DeployedAt`; we don't unwind them.
    function _carriedForwardTopLevelStamps(string memory raw)
        internal
        pure
        returns (string memory body)
    {
        string[] memory keys = vm.parseJsonKeys(raw, ".");
        for (uint256 i = 0; i < keys.length; i++) {
            string memory k = keys[i];
            if (_isWellKnownTopLevelKey(k)) continue;
            uint256 v = vm.parseJsonUint(raw, string.concat(".", k));
            body = string.concat(body, '  "', k, '": ', vm.toString(v), ",\n");
        }
    }

    function _phase3Addresses(Phase3Addresses memory a) internal pure returns (string memory) {
        return string.concat(
            _kv("helixAllocatorVault", a.helixAllocatorVault),
            _kvLast("helixAllocatorId", a.helixAllocatorId)
        );
    }

    function _isPhase3OverrideKey(string memory k) internal pure returns (bool) {
        bytes32 h = keccak256(bytes(k));
        return h == keccak256("helixAllocatorVault") || h == keccak256("helixAllocatorId");
    }

    function _isWellKnownTopLevelKey(string memory k) internal pure returns (bool) {
        bytes32 h = keccak256(bytes(k));
        return h == keccak256("chainId") || h == keccak256("deployedAt") || h == keccak256("phase")
            || h == keccak256("addresses") || h == keccak256("phase3DeployedAt");
    }

    function _kv(string memory k, address v) internal pure returns (string memory) {
        return string.concat('    "', k, '": "', _addrLower(v), '",\n');
    }

    function _kvLast(string memory k, address v) internal pure returns (string memory) {
        return string.concat('    "', k, '": "', _addrLower(v), '"\n');
    }

    function _logAddresses(Phase3Addresses memory a) internal view {
        console2.log("=== Helios Phase-3 deploy ===");
        console2.log("chainId:                 ", block.chainid);
        console2.log("Helix AllocatorVault:    ", a.helixAllocatorVault);
        console2.log("Helix allocatorId:       ", a.helixAllocatorId);
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
