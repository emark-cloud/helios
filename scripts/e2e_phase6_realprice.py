"""WS7 — Phase-6 real-price e2e assertion harness.

Asserts the multi-asset real-price cutover landed correctly on Kite
testnet. Companion to `docs/phase6-realprice-plan.md` §Verification.

The script runs in two phases:

  1. Static health checks (always required post-WS8):
       - `phase6Vaults` + `testAssets` blocks present in the
         deployment JSON.
       - Each Phase-6 StrategyVault is `active=true` in the
         StrategyRegistry.
       - `MockSwapRouter.priceOf(USDC, asset)` is non-zero for at
         least one universe leg → confirms the WS2 keeper has
         posted a price within the last bar.

  2. Driving phase (gated on `DEPOSITOR_PK`): deposit ~$1k, wait up
     to `PHASE6_OBSERVE_SECS` seconds for a `Swapped` event from the
     MockSwapRouter, assert at least one Phase-6 StrategyVault's
     `totalNAV()` differs from the deposited amount by ≥ 1 bps.

`SKIP_ON_PRE_WS8=1` (default) makes the static phase exit 0 with a
clear "WS8 broadcast required" message when `phase6Vaults` is
missing — so the script can sit on `main` without breaking CI
pre-broadcast. Flip to `0` to fail loudly during the broadcast
window.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

from eth_account import Account
from web3 import Web3
from web3.contract import Contract

# Inlined ABI fragments — `helios_contracts_abi` does not export
# MockSwapRouter (it's a test mock, not a public surface). The
# StrategyRegistry and StrategyVault fragments below are scoped to
# the read-only methods we need; the full ABIs live in
# `packages/contracts-abi/src/abis/`.
_MOCK_SWAP_ROUTER_ABI = [
    {
        "type": "function",
        "name": "priceOf",
        "stateMutability": "view",
        "inputs": [
            {"name": "tokenIn", "type": "address"},
            {"name": "tokenOut", "type": "address"},
        ],
        "outputs": [
            {
                "name": "",
                "type": "tuple",
                "components": [
                    {"name": "num", "type": "uint256"},
                    {"name": "denom", "type": "uint256"},
                ],
            }
        ],
    },
    {
        "type": "event",
        "name": "Swapped",
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "payer", "type": "address"},
            {"indexed": True, "name": "recipient", "type": "address"},
            {"indexed": True, "name": "tokenIn", "type": "address"},
            {"indexed": False, "name": "tokenOut", "type": "address"},
            {"indexed": False, "name": "amountIn", "type": "uint256"},
            {"indexed": False, "name": "amountOut", "type": "uint256"},
        ],
    },
]

_REGISTRY_STRATEGY_OF_ABI = [
    {
        "type": "function",
        "name": "strategyOf",
        "stateMutability": "view",
        "inputs": [{"name": "strategyId", "type": "address"}],
        "outputs": [
            {
                "name": "",
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
    }
]

_STRATEGY_VAULT_TOTAL_NAV_ABI = [
    {
        "type": "function",
        "name": "totalNAV",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
    }
]


@dataclass(frozen=True)
class Ctx:
    w3: Web3
    addrs: dict[str, Any]
    phase6_vaults: dict[str, str]
    test_assets: dict[str, str]
    swap_router: str


def _exit_skip(msg: str) -> NoReturn:
    print(f"[phase6-realprice] SKIP — {msg}")
    sys.exit(0)


def _exit_fail(msg: str) -> NoReturn:
    print(f"[phase6-realprice] FAIL — {msg}")
    sys.exit(1)


def _load(deployments: Path) -> Ctx:
    if not deployments.is_file():
        _exit_fail(f"deployments file not found: {deployments}")
    raw = json.loads(deployments.read_text())
    addrs = raw.get("addresses") or {}
    swap_router = addrs.get("swapRouter") or ""

    # The Phase-6 deploy scripts write flat keys under `addresses`:
    #   phase6Vault{Class}[Variant{2,3}] for each of the nine vaults
    #   mWbtc / mWeth / mSol           for the universe asset trio
    # Lift them back into convenient sub-dicts so the rest of the
    # harness can reason about them as logical blocks.
    phase6: dict[str, str] = {
        k: v for k, v in addrs.items() if isinstance(k, str) and k.startswith("phase6Vault")
    }
    test_assets: dict[str, str] = {k: addrs[k] for k in ("mWbtc", "mWeth", "mSol") if k in addrs}

    skip_pre_ws8 = os.environ.get("SKIP_ON_PRE_WS8", "1") != "0"
    if not phase6 or not test_assets:
        msg = (
            "phase6Vault* and/or mWbtc/mWeth/mSol missing from "
            "deployments.addresses — run DeployTestUniverse + "
            "DeployPhase6MultiAssetVaults first (see "
            "docs/phase6-realprice-plan.md §Sequence)."
        )
        if skip_pre_ws8:
            _exit_skip(msg)
        _exit_fail(msg)

    rpc = os.environ.get("KITE_RPC_URL") or os.environ.get("RPC_URL", "")
    if not rpc:
        _exit_fail("KITE_RPC_URL (or RPC_URL) must be set")
    w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 15}))
    if not w3.is_connected():
        _exit_fail(f"RPC not reachable: {rpc}")
    return Ctx(
        w3=w3,
        addrs=addrs,
        phase6_vaults=phase6,
        test_assets=test_assets,
        swap_router=swap_router,
    )


def _check_registry(ctx: Ctx) -> None:
    """Every Phase-6 vault must be `active=true`. Catches the "deploy ran
    but registerStrategy reverted silently" failure mode."""
    registry_addr = ctx.addrs.get("strategyRegistry")
    if not registry_addr:
        _exit_fail("strategyRegistry address missing from deployments.addresses")
    registry: Contract = ctx.w3.eth.contract(
        address=Web3.to_checksum_address(registry_addr),
        abi=_REGISTRY_STRATEGY_OF_ABI,
    )
    inactive: list[str] = []
    for label, addr in ctx.phase6_vaults.items():
        if not addr:
            _exit_fail(f"phase6Vaults.{label} is empty")
        entry = registry.functions.strategyOf(Web3.to_checksum_address(addr)).call()
        # entry tuple per _REGISTRY_STRATEGY_OF_ABI; index 6 = active.
        if not entry[6]:
            inactive.append(f"{label} {addr}")
    if inactive:
        _exit_fail(
            "Phase-6 vault(s) not active in StrategyRegistry: "
            + ", ".join(inactive)
            + " — DeployPhase6MultiAssetVaults must call registerStrategy "
            "for each proxy."
        )
    print(f"[phase6-realprice] OK — {len(ctx.phase6_vaults)} Phase-6 vaults active in registry")


def _check_router_prices(ctx: Ctx) -> None:
    """At least one (USDC, asset) leg on MockSwapRouter must have a
    non-zero price. Confirms the WS2 RouterPriceMirror keeper is
    landing snapshots."""
    if not ctx.swap_router:
        _exit_fail("swapRouter address missing from deployments.addresses")
    router: Contract = ctx.w3.eth.contract(
        address=Web3.to_checksum_address(ctx.swap_router),
        abi=_MOCK_SWAP_ROUTER_ABI,
    )
    usdc: str = ctx.addrs.get("usdc") or ""
    if not usdc:
        _exit_fail("usdc address missing from deployments.addresses")
    legs = [
        ("WBTC", ctx.test_assets.get("mWbtc")),
        ("WETH", ctx.test_assets.get("mWeth")),
        ("WSOL", ctx.test_assets.get("mSol")),
    ]
    priced: list[str] = []
    for name, addr in legs:
        if not addr:
            continue
        price = router.functions.priceOf(
            Web3.to_checksum_address(usdc), Web3.to_checksum_address(addr)
        ).call()
        # price = (num, denom) — both > 0 means setPrice has fired
        if price[0] > 0 and price[1] > 0:
            priced.append(name)
    if not priced:
        _exit_fail(
            "MockSwapRouter has no priced legs — RouterPriceMirror "
            "keeper has not posted a snapshot. Check ROUTER_MIRROR_ENABLED=1, "
            "ROUTER_MIRROR_TOKEN_USDC, and the oracle service log."
        )
    print(f"[phase6-realprice] OK — MockSwapRouter has prices for {priced}")


def _drive_deposit_and_observe(ctx: Ctx) -> None:
    """Optional driving phase. Gated on DEPOSITOR_PK. Asserts at
    least one Swapped event lands within PHASE6_OBSERVE_SECS and at
    least one Phase-6 vault's totalNAV() moves by ≥ 1 bps from the
    deposit amount. Skipped when DEPOSITOR_PK is unset."""
    pk = os.environ.get("DEPOSITOR_PK", "")
    if not pk:
        print("[phase6-realprice] SKIP driving phase — set DEPOSITOR_PK to enable")
        return

    observe_secs = int(os.environ.get("PHASE6_OBSERVE_SECS", "300"))
    deposit_amount_e18 = int(os.environ.get("PHASE6_DEPOSIT_AMOUNT", str(1_000 * 10**18)))

    depositor = Account.from_key(pk if pk.startswith("0x") else "0x" + pk)
    print(
        f"[phase6-realprice] driving deposit from {depositor.address} "
        f"for {deposit_amount_e18 / 10**18:.2f} USDC"
    )

    # Snapshot pre-deposit NAV per Phase-6 vault.
    pre_nav = _read_phase6_nav(ctx)

    _send_deposit(ctx, depositor, deposit_amount_e18)

    # Observe Swapped events on MockSwapRouter for up to observe_secs.
    router: Contract = ctx.w3.eth.contract(
        address=Web3.to_checksum_address(ctx.swap_router),
        abi=_MOCK_SWAP_ROUTER_ABI,
    )
    start_block = ctx.w3.eth.block_number
    deadline = time.monotonic() + observe_secs
    swap_count = 0
    while time.monotonic() < deadline:
        head = ctx.w3.eth.block_number
        if head > start_block:
            logs = router.events.Swapped().get_logs(from_block=start_block + 1, to_block=head)
            swap_count += len(logs)
            start_block = head
            if swap_count > 0:
                # One swap is enough to assert the keeper + witness fix
                # both landed; we wait a bit more for NAV to settle.
                break
        time.sleep(5)

    if swap_count == 0:
        _exit_fail(
            f"no Swapped events on MockSwapRouter within {observe_secs}s — "
            "allocator/strategy/prover pipeline is not closing. Check "
            "sentinel rank loop, prover health, and momentum/mean_rev "
            "service logs."
        )
    print(f"[phase6-realprice] OK — observed {swap_count} Swapped event(s)")

    # Wait one bar for NAV to settle, then assert movement.
    time.sleep(int(os.environ.get("PHASE6_NAV_SETTLE_SECS", "70")))
    post_nav = _read_phase6_nav(ctx)

    bps_moved = []
    for label in ctx.phase6_vaults:
        before = pre_nav.get(label, 0)
        after = post_nav.get(label, 0)
        if before == 0:
            continue
        delta_bps = (after - before) * 10_000 // before
        if abs(delta_bps) >= 1:
            bps_moved.append(f"{label}: {delta_bps:+d} bps")

    if not bps_moved:
        _exit_fail(
            "no Phase-6 vault NAV moved ≥1 bps after deposit + swap — "
            "indicates witness asset_decimals threading or RouterPriceMirror "
            "math is wrong. Check MOMENTUM_ASSET_DECIMALS_JSON / "
            "MEAN_REV_ASSET_DECIMALS_JSON in /srv/helios/.env."
        )
    print(f"[phase6-realprice] OK — NAV moved on: {bps_moved}")


def _read_phase6_nav(ctx: Ctx) -> dict[str, int]:
    out: dict[str, int] = {}
    for label, addr in ctx.phase6_vaults.items():
        if not addr:
            continue
        vault = ctx.w3.eth.contract(
            address=Web3.to_checksum_address(addr),
            abi=_STRATEGY_VAULT_TOTAL_NAV_ABI,
        )
        try:
            out[label] = vault.functions.totalNAV().call()
        except Exception as exc:
            print(f"[phase6-realprice] WARN — {label} totalNAV() reverted: {exc}")
    return out


def _send_deposit(_ctx: Ctx, _depositor: object, _amount_e18: int) -> None:
    """UserVault.deposit + delegate path. Deferred to a Passport-aware
    helper post-WS8; for now, fail fast with a pointer."""
    raise NotImplementedError(
        "deposit driving requires Passport session wiring — "
        "use the frontend or `kpass` CLI to deposit, then re-run with "
        "DEPOSITOR_PK unset to skip the driving phase."
    )


def main() -> int:
    deployments = Path(
        os.environ.get("DEPLOYMENTS_FILE", "contracts/deployments/kite-testnet.json")
    )
    print(f"[phase6-realprice] using deployments: {deployments}")
    ctx = _load(deployments)
    _check_registry(ctx)
    _check_router_prices(ctx)
    _drive_deposit_and_observe(ctx)
    print("[phase6-realprice] acceptance: GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
