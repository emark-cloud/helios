"""DEPRECATED — historical Phase-3 smoke check. Will fail post-cutover.

This script asserts that `strategyVaultMomentum/MeanReversion/YieldRotation`
(the Phase-3 base-trio fresh-redeploy proxies) are `active=true` in
`StrategyRegistry`. The 2026-05-09 Phase-6 real-price cutover flipped
those proxies to `active=false`; the canonical active set lives under
`phase6Vault*` keys. Use `scripts/e2e_phase6_realprice.py` (via
`./scripts/e2e-scenario.sh phase6-realprice`) for the current
acceptance harness.

Kept on disk so the Phase-3 acceptance trail is reproducible against
historical RPC state if anyone needs to forensically replay it; the
new harness has different invariants and can't substitute.

Original spec: read-only smoke check for the Phase-3 base-trio fresh
redeploy (2026-05-08). Confirmed each new strategy proxy was on the
Phase-3 impl, registered + active, `paused()` callable (proves the
Pausable mixin is live), and that its manifest / constructor
immutables matched the redeploy convention. Also probed UserVault +
AllocatorVault for the same Phase-3 surface (`paused()`,
`userTotalDeployed`). Drove no transactions.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from web3 import Web3

# EIP-1967 implementation slot — keccak256("eip1967.proxy.implementation") - 1.
_IMPL_SLOT = int(
    "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc",
    16,
)

# Order matches contracts/script/RedeployBaseTrioStrategyVaults.s.sol.
_BASE_TRIO: tuple[tuple[str, str, str], ...] = (
    ("strategyVaultMomentum", "momentum_v1", "helios.mom_v1.base.phase3-redeploy"),
    ("strategyVaultMeanReversion", "mean_reversion_v1", "helios.mr_v1.base.phase3-redeploy"),
    ("strategyVaultYieldRotation", "yield_rotation_v1", "helios.yr_v1.base.phase3-redeploy"),
)

# Pre-redeploy base-trio impl addresses from project memory — used to
# refuse a green check if a proxy somehow rolled back to the legacy 5-slot
# manifest impl.
_LEGACY_BASE_IMPLS: frozenset[str] = frozenset(
    {
        "0xd49ca44645e21076dcd83f285d23c99abeb6d299",  # momentum
        "0x757ae165557d45c5d729312324cff7ff41063d41",  # mean-rev
        "0x2d036e311a6f11f8abd191276fd381df55fbe224",  # yield-rot
    }
)

# Minimal ABIs — only the methods we read.
_STRATEGY_VAULT_ABI = [
    {
        "name": "paused",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"type": "bool"}],
    },
    {
        "name": "priceAnchor",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"type": "address"}],
    },
    {
        "name": "yieldAnchor",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"type": "address"}],
    },
    {
        "name": "manifest",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [
            {
                "type": "tuple",
                "components": [
                    {"name": "declaredClass", "type": "bytes32"},
                    {"name": "assetUniverse", "type": "address[]"},
                    {"name": "maxCapacity", "type": "uint256"},
                    {"name": "feeRateBps", "type": "uint16"},
                    {"name": "operator", "type": "address"},
                    {"name": "stakeAmount", "type": "uint256"},
                    {"name": "paramsHash", "type": "bytes32"},
                ],
            }
        ],
    },
]

_REGISTRY_ABI = [
    {
        "name": "strategyOf",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"type": "address"}],
        "outputs": [
            {
                "type": "tuple",
                "components": [
                    {"name": "vault", "type": "address"},
                    {"name": "operator", "type": "address"},
                    {"name": "declaredClass", "type": "bytes32"},
                    {"name": "stakeAmount", "type": "uint256"},
                    {"name": "currentReputation", "type": "int256"},
                    {"name": "registeredAt", "type": "uint64"},
                    {"name": "active", "type": "bool"},
                ],
            }
        ],
    },
]

_PAUSABLE_ABI = [
    {
        "name": "paused",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"type": "bool"}],
    },
]

_ALLOCATOR_VAULT_VIEWS_ABI = [
    *_PAUSABLE_ABI,
    {
        "name": "userTotalDeployed",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"type": "address"}],
        "outputs": [{"type": "uint256"}],
    },
]


class SmokeFail(Exception):
    """Raised when any assertion fails — main() converts to exit code 1."""


def _ok(msg: str) -> None:
    print(f"  \033[32m✓\033[0m {msg}")


def _fail(msg: str) -> None:
    print(f"  \033[31m✗\033[0m {msg}", file=sys.stderr)


def _impl_slot(w3: Web3, proxy: str) -> str:
    raw = w3.eth.get_storage_at(Web3.to_checksum_address(proxy), _IMPL_SLOT)
    return Web3.to_checksum_address("0x" + raw.hex()[-40:])


def _check_proxied_pausable(w3: Web3, label: str, proxy: str, view_abi: list[dict]) -> None:
    impl = _impl_slot(w3, proxy)
    if int(impl, 16) == 0:
        raise SmokeFail(f"{label}: EIP-1967 impl slot is zero (proxy not initialized)")
    print(f"\n[{label}] proxy={proxy}")
    _ok(f"impl slot points at {impl}")

    contract = w3.eth.contract(address=Web3.to_checksum_address(proxy), abi=view_abi)
    try:
        paused = contract.functions.paused().call()
    except Exception as exc:
        raise SmokeFail(
            f"{label}: paused() reverted — Phase-3 Pausable mixin not live ({exc})"
        ) from exc
    _ok(f"paused() = {paused} (Pausable mixin live)")
    if paused:
        # Not a smoke failure per se, but worth flagging — the testnet
        # shouldn't be sitting paused under normal conditions.
        _fail(f"{label}: paused=True — operator should unpause before further e2e runs")


def _check_base_proxy(
    w3: Web3,
    addrs: dict[str, str],
    registry,  # web3 contract
    json_key: str,
    expected_class_label: str,
    params_seed: str,
) -> None:
    proxy = addrs[json_key]
    print(f"\n[{json_key}] proxy={proxy}  class={expected_class_label}")

    impl = _impl_slot(w3, proxy)
    if impl.lower() in {a.lower() for a in _LEGACY_BASE_IMPLS}:
        raise SmokeFail(
            f"{json_key}: impl slot {impl} matches a known legacy base-trio impl — "
            "the Phase-3 redeploy did not stick or the proxy was rolled back"
        )
    _ok(f"impl slot {impl} (not legacy)")

    vault = w3.eth.contract(address=Web3.to_checksum_address(proxy), abi=_STRATEGY_VAULT_ABI)

    # paused() — Phase-3 impl exposes Pausable mixin.
    try:
        paused = vault.functions.paused().call()
    except Exception as exc:
        raise SmokeFail(f"{json_key}: paused() reverted — not on Phase-3 impl ({exc})") from exc
    _ok(f"paused() = {paused}")

    # manifest paramsHash matches the redeploy convention.
    manifest = vault.functions.manifest().call()
    declared_class = manifest[0]
    operator = manifest[4]
    params_hash = manifest[6]
    expected_params_hash = Web3.keccak(text=params_seed)
    if bytes(params_hash) != expected_params_hash:
        raise SmokeFail(
            f"{json_key}: manifest.paramsHash = 0x{bytes(params_hash).hex()}, "
            f"expected 0x{expected_params_hash.hex()} (keccak256({params_seed!r}))"
        )
    _ok(f"manifest.paramsHash = keccak256({params_seed!r})")

    if int.from_bytes(declared_class, "big") == 0:
        raise SmokeFail(f"{json_key}: declaredClass is zero — bad init")
    _ok(f"declaredClass = 0x{bytes(declared_class).hex()[:12]}…")

    # Constructor-immutable anchors must match the JSON's redeployed anchors.
    expected_price = Web3.to_checksum_address(addrs["oraclePriceAnchor"])
    expected_yield = Web3.to_checksum_address(addrs["oracleYieldAnchor"])
    actual_price = vault.functions.priceAnchor().call()
    actual_yield = vault.functions.yieldAnchor().call()
    if Web3.to_checksum_address(actual_price) != expected_price:
        raise SmokeFail(
            f"{json_key}: priceAnchor immutable = {actual_price}, expected {expected_price}"
        )
    if Web3.to_checksum_address(actual_yield) != expected_yield:
        raise SmokeFail(
            f"{json_key}: yieldAnchor immutable = {actual_yield}, expected {expected_yield}"
        )
    _ok("priceAnchor / yieldAnchor immutables wired to Phase-3 oracle anchors")

    # Registered + active.
    entry = registry.functions.strategyOf(Web3.to_checksum_address(proxy)).call()
    entry_operator = entry[1]
    entry_class = entry[2]
    active = entry[6]
    if not active:
        raise SmokeFail(f"{json_key}: not active in StrategyRegistry")
    if Web3.to_checksum_address(entry_operator) != Web3.to_checksum_address(operator):
        raise SmokeFail(
            f"{json_key}: registry.operator {entry_operator} != manifest.operator {operator}"
        )
    if bytes(entry_class) != bytes(declared_class):
        raise SmokeFail(
            f"{json_key}: registry.declaredClass != manifest.declaredClass — corruption?"
        )
    _ok("registered + active in StrategyRegistry; operator/class consistent")


def _check_allocator_vault(w3: Web3, proxy: str) -> None:
    _check_proxied_pausable(w3, "AllocatorVault", proxy, _ALLOCATOR_VAULT_VIEWS_ABI)
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(proxy), abi=_ALLOCATOR_VAULT_VIEWS_ABI
    )
    try:
        result = contract.functions.userTotalDeployed(
            "0x0000000000000000000000000000000000000000"
        ).call()
    except Exception as exc:
        raise SmokeFail(
            f"AllocatorVault.userTotalDeployed() reverted — Phase-3 Unit-1 view not live ({exc})"
        ) from exc
    _ok(f"userTotalDeployed(0) = {result} (HIGH #5/#8 view live)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rpc-url",
        default=os.environ.get("KITE_RPC_URL"),
        help="Kite testnet RPC URL (defaults to $KITE_RPC_URL).",
    )
    parser.add_argument(
        "--deployments",
        default="contracts/deployments/kite-testnet.json",
        help="Path to the kite-testnet.json deployments file.",
    )
    args = parser.parse_args()

    if not args.rpc_url:
        print("error: --rpc-url or $KITE_RPC_URL must be set", file=sys.stderr)
        return 2

    deployments_path = Path(args.deployments)
    if not deployments_path.is_file():
        print(f"error: deployments file not found at {deployments_path}", file=sys.stderr)
        return 2

    raw = json.loads(deployments_path.read_text())
    addrs: dict[str, str] = raw["addresses"]

    w3 = Web3(Web3.HTTPProvider(args.rpc_url, request_kwargs={"timeout": 30}))
    chain_id = w3.eth.chain_id
    if chain_id != 2368:
        print(
            f"error: connected chainId {chain_id} != 2368 (Kite testnet)",
            file=sys.stderr,
        )
        return 2

    print("=== Phase-3 base-trio smoke ===")
    print(f"chainId:      {chain_id}")
    print(f"rpc:          {args.rpc_url}")
    print(f"deployments:  {deployments_path}")
    print(f"phase3BaseTrioRedeployedAt: {raw.get('phase3BaseTrioRedeployedAt')}")

    registry = w3.eth.contract(
        address=Web3.to_checksum_address(addrs["strategyRegistry"]),
        abi=_REGISTRY_ABI,
    )

    failures = 0

    # UserVault + AllocatorVault Phase-3 surface (Unit-1 follow-up).
    for label, key, abi in (
        ("UserVault", "userVault", _PAUSABLE_ABI),
        ("AllocatorVault", "allocatorVault", _ALLOCATOR_VAULT_VIEWS_ABI),
    ):
        try:
            if label == "AllocatorVault":
                _check_allocator_vault(w3, addrs[key])
            else:
                _check_proxied_pausable(w3, label, addrs[key], abi)
        except SmokeFail as exc:
            _fail(str(exc))
            failures += 1

    # Base trio fresh redeploys.
    for json_key, expected_class, params_seed in _BASE_TRIO:
        if json_key not in addrs:
            _fail(f"{json_key}: missing from deployments JSON")
            failures += 1
            continue
        try:
            _check_base_proxy(w3, addrs, registry, json_key, expected_class, params_seed)
        except SmokeFail as exc:
            _fail(str(exc))
            failures += 1

    print()
    if failures:
        print(f"\033[31mFAIL\033[0m — {failures} assertion(s) failed", file=sys.stderr)
        return 1
    print("\033[32mGREEN\033[0m — all Phase-3 follow-up surfaces healthy on Kite testnet")
    return 0


if __name__ == "__main__":
    sys.exit(main())
