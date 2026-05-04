"""WS6 — Phase 2 e2e scenario orchestrator (PR1 skeleton).

Drives the deploy + meta-strategy + allocation surface against a Phase
2 stack (DeployPhase1 → DeployPhase2 → RegisterPhase2Strategies):

  fund user with mUSDC
  → user signs meta-strategy with all 3 classes allowed (Passport stub)
  → deposit + delegate to AllocatorVault
  → operator allocates to all 6 strategy vaults (2 per class)
  → assert 6 AllocationCreated logs

PR1 stops here. Real trade flows + reputation engine assertions land in
PR2 and PR3 respectively. The 200-bar oracle replay
(`scenarios/phase2-multi-class.json`) is read by the oracle service in
scenario mode but is not consumed by this script directly — the
scenario fixture is part of the e2e env, not the orchestrator's API.

Track A (default): invoked by `scripts/e2e-scenario-phase2.sh` against
a fresh anvil-kite. Mock-Groth16 verifiers are NOT in play in Phase 2
— `DeployPhase2` swapped in the real per-class adapters at registration
time. Trade flows still aren't exercised in this PR; PR2 wires the
prover service for that.

Track B: same script with `RPC_URL=$KITE_RPC_URL` + `DEPLOYER_PK=...`
+ `OUT_LABEL=kite-testnet` in env. Broadcasts to Kite testnet and
patches the existing `kite-testnet.json` deployment file in place.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils.crypto import keccak
from helios_contracts_abi import (
    MEAN_REVERSION_V1 as CLASS_MR_BYTES32,
)
from helios_contracts_abi import (
    MOMENTUM_V1 as CLASS_MOM_BYTES32,
)
from helios_contracts_abi import (
    YIELD_ROTATION_V1 as CLASS_YR_BYTES32,
)
from helios_contracts_abi.abis import (
    IAllocatorVault_ABI,
    IOracleAnchor_ABI,
    IStrategyRegistry_ABI,
    IStrategyVault_ABI,
    IUserVault_ABI,
)
from web3 import Web3
from web3.contract.contract import Contract

# Local witness builder + proof helpers. `scripts/_phase2_witness.py`
# lives next to this file; ensure the dir is on the path so imports
# resolve when we're invoked from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _phase2_oracle_nav import (
    ANCHOR_COMMITS_PER_ANCHOR,
    DAY_SEC,
    NAV_SAMPLES_PER_VAULT,
    NavTrajectoryDriver,
    OracleAnchorDriver,
)
from _phase2_reputation_local import LocalGoldskyStub
from _phase2_witness import (
    build_mean_reversion_witness,
    build_momentum_witness,
    build_yield_rotation_witness,
)

# Reuse the helios-cli encoder for proof bytes — single source of truth
# for the snarkjs Fp2 imag/real swap. Available via uv workspace.
from helios_cli._proof import (
    proof_to_bytes,
    public_signals_to_uints,
)

# Reputation engine (workspace package). Imported here only — the engine
# is async-driven from `step_drive_reputation` via `asyncio.run`.
from reputation.engine import EngineUpdate, ReputationEngine
from reputation.signer import ActorType, ReputationSigner

# ── Anvil default keys (deterministic mnemonic).
# Operator = anvil[0] = deployer per DeployPhase1.s.sol.
# User     = anvil[1] (the [PASSPORT-STUB]).
_OPERATOR_PK = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
_USER_PK = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"

# Standard ERC20 mint(address,uint256) — mock USDC exposes it.
_ERC20_MINT_ABI = [
    {
        "type": "function",
        "name": "mint",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "to", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [],
    },
    {
        "type": "function",
        "name": "approve",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "type": "function",
        "name": "balanceOf",
        "stateMutability": "view",
        "inputs": [{"name": "owner", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
]

# 6 strategy vault keys in canonical order (2 per class).
_STRATEGY_VAULT_KEYS: tuple[tuple[str, str], ...] = (
    ("strategyVaultMomentum", "momentum_v1"),
    ("strategyVaultMomentumVariant2", "momentum_v1"),
    ("strategyVaultMeanReversion", "mean_reversion_v1"),
    ("strategyVaultMeanReversionVariant2", "mean_reversion_v1"),
    ("strategyVaultYieldRotation", "yield_rotation_v1"),
    ("strategyVaultYieldRotationVariant2", "yield_rotation_v1"),
)

# WS7.B fresh strategy — 7th vault, zero track record, registered by
# `contracts/script/RegisterFreshStrategy.s.sol` after the main 6.
# Excluded from `_STRATEGY_VAULT_KEYS` so steps iterating those (NAV,
# trades, allocation) skip it; it's only consumed in PR3.5.C's
# bootstrap-pool drive.
_FRESH_STRATEGY_KEY = "strategyVaultMomentumVariant3"
_FRESH_STRATEGY_CLASS = "momentum_v1"

_DEPOSIT_USDC = 60_000  # 60k mUSDC: enough to allocate 5k × 6 with idle headroom.
_ALLOC_PER_STRATEGY_USDC = 5_000


@dataclass
class Ctx:
    w3: Web3
    chain_id: int
    addrs: dict[str, str]
    deployer: Any
    user: Any
    user_vault: Contract
    allocator_vault: Contract
    strategy_registry: Contract
    strategy_vaults: list[Contract]
    oracle_price_anchor: Contract
    oracle_yield_anchor: Contract
    usdc: Contract
    prover_url: str
    # Synthetic now-of-the-scenario in unix seconds. Used to anchor
    # both the NAV trajectory daily samples (PR3.A) and the
    # reputation engine's 90d slice (PR3.B). Set in `_setup`.
    synthetic_now_sec: int = 0


# ── Setup ────────────────────────────────────────────────────


def _load_addresses(path: Path) -> dict[str, str]:
    with path.open() as f:
        return json.load(f)["addresses"]


def _wait_for_rpc(rpc_url: str, timeout_sec: int = 30) -> Web3:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 2}))
            if w3.is_connected() and w3.eth.block_number >= 0:
                return w3
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"RPC at {rpc_url} did not become ready in {timeout_sec}s")


def _send(w3: Web3, account: Any, fn: Any, *, gas_buffer: float = 1.2) -> dict[str, Any]:
    tx = fn.build_transaction(
        {
            "from": account.address,
            "nonce": w3.eth.get_transaction_count(account.address, "pending"),
            "chainId": w3.eth.chain_id,
            "gasPrice": w3.eth.gas_price,
        }
    )
    if "gas" in tx:
        tx["gas"] = int(tx["gas"] * gas_buffer)
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
    if receipt["status"] != 1:
        raise RuntimeError(f"tx reverted: {tx_hash.hex()}")
    return dict(receipt)


def _setup(rpc_url: str, deployments: Path, prover_url: str) -> Ctx:
    w3 = _wait_for_rpc(rpc_url)
    chain_id = w3.eth.chain_id
    addrs = _load_addresses(deployments)
    deployer = Account.from_key(_OPERATOR_PK)
    user = Account.from_key(_USER_PK)

    # Verify the deployment file has all 6 strategy vaults — fail loud
    # if RegisterPhase2Strategies didn't run.
    missing = [k for (k, _cls) in _STRATEGY_VAULT_KEYS if k not in addrs]
    if missing:
        raise RuntimeError(
            f"deployments file missing variant2 keys {missing!r}; "
            "did RegisterPhase2Strategies.s.sol run?"
        )

    user_vault = w3.eth.contract(
        address=Web3.to_checksum_address(addrs["userVault"]), abi=IUserVault_ABI
    )
    allocator_vault = w3.eth.contract(
        address=Web3.to_checksum_address(addrs["allocatorVault"]), abi=IAllocatorVault_ABI
    )
    strategy_registry = w3.eth.contract(
        address=Web3.to_checksum_address(addrs["strategyRegistry"]),
        abi=IStrategyRegistry_ABI,
    )
    strategy_vaults = [
        w3.eth.contract(
            address=Web3.to_checksum_address(addrs[key]),
            abi=IStrategyVault_ABI,
        )
        for (key, _cls) in _STRATEGY_VAULT_KEYS
    ]
    usdc = w3.eth.contract(
        address=Web3.to_checksum_address(addrs["usdc"]),
        abi=_ERC20_MINT_ABI,
    )
    # Phase 2 oracle anchors come from `DeployPhase2.s.sol::_deployAnchors`.
    # Pre-PR3, the e2e didn't reference them — gate so a Phase-1-only
    # deployments file produces a clear error if PR3 ever runs against it.
    for k in ("oraclePriceAnchor", "oracleYieldAnchor"):
        if k not in addrs:
            raise RuntimeError(f"deployments file missing {k!r}; did DeployPhase2.s.sol run?")
    oracle_price_anchor = w3.eth.contract(
        address=Web3.to_checksum_address(addrs["oraclePriceAnchor"]),
        abi=IOracleAnchor_ABI,
    )
    oracle_yield_anchor = w3.eth.contract(
        address=Web3.to_checksum_address(addrs["oracleYieldAnchor"]),
        abi=IOracleAnchor_ABI,
    )
    return Ctx(
        w3=w3,
        chain_id=chain_id,
        addrs=addrs,
        deployer=deployer,
        user=user,
        user_vault=user_vault,
        allocator_vault=allocator_vault,
        strategy_registry=strategy_registry,
        strategy_vaults=strategy_vaults,
        oracle_price_anchor=oracle_price_anchor,
        oracle_yield_anchor=oracle_yield_anchor,
        usdc=usdc,
        prover_url=prover_url,
        # Pin the scenario clock to wall-clock now. NAV trajectories
        # span [-29d, 0d] from this point; the reputation engine's 90d
        # window cutoff (ts - 90d) is also computed against this anchor
        # in PR3.B.
        synthetic_now_sec=int(time.time()),
    )


# ── Steps ────────────────────────────────────────────────────


def step_fund(ctx: Ctx) -> None:
    print(f"[1] fund user with {_DEPOSIT_USDC // 1000}k mUSDC")
    _send(ctx.w3, ctx.deployer, ctx.usdc.functions.mint(ctx.user.address, _DEPOSIT_USDC * 10**6))
    bal = ctx.usdc.functions.balanceOf(ctx.user.address).call()
    assert bal == _DEPOSIT_USDC * 10**6, f"user mUSDC balance {bal} unexpected"


def step_set_meta(ctx: Ctx) -> bytes:
    """User signs + posts a meta-strategy permitting all 3 Phase 2 classes
    and up to 6 concurrent strategies. [PASSPORT-STUB] for the EIP-712
    signature — UserVault.setMetaStrategy doesn't verify in Phase 1/2.
    """
    print("[2] user setMetaStrategy (3 classes, maxStrategiesCount=6)")
    meta_struct = (
        keccak(b"phase2-demo-meta"),  # metaStrategyHash
        [CLASS_MOM_BYTES32, CLASS_MR_BYTES32, CLASS_YR_BYTES32],  # allowedStrategyClasses
        [Web3.to_checksum_address(ctx.addrs["usdc"])],  # allowedAssets
        [ctx.chain_id],  # allowedChains
        _DEPOSIT_USDC * 10**6,  # maxCapital
        5_000,  # maxPerStrategyBps (50% — leaves headroom for 6 splits)
        6,  # maxStrategiesCount
        2_000,  # drawdownThresholdBps (20% — looser than Phase 1's 15% so the
        #                                  KITE drawdown leg in PR2 still triggers
        #                                  defund cleanly without false-firing)
        2_500,  # maxFeeRateBps
        3_600,  # rebalanceCadenceSec (1h)
        0,  # validUntil (never expires)
        # WS7.C — auto-defund knobs. Zeros = use UserVault defaults
        # (twapBars=3, bondBps=50, confirmBlocks=25 per
        # `MetaStrategyLib.DEFAULT_DEFUND_*`).
        0,  # defundTwapBars
        0,  # defundBondBps
        0,  # defundConfirmBlocks
    )
    domain = {
        "name": "HeliosUserVault",
        "version": "1",
        "chainId": ctx.chain_id,
        "verifyingContract": Web3.to_checksum_address(ctx.addrs["userVault"]),
    }
    types = {
        "MetaStrategyAck": [
            {"name": "metaStrategyHash", "type": "bytes32"},
            {"name": "validUntil", "type": "uint64"},
        ]
    }
    message = {"metaStrategyHash": meta_struct[0], "validUntil": 0}
    encoded = encode_typed_data(domain_data=domain, message_types=types, message_data=message)
    sig = ctx.user.sign_message(encoded).signature

    _send(ctx.w3, ctx.user, ctx.user_vault.functions.setMetaStrategy(meta_struct, sig))
    return sig


def step_deposit_and_delegate(ctx: Ctx) -> None:
    print(f"[3] user approve + deposit {_DEPOSIT_USDC // 1000}k mUSDC + delegate to AllocatorVault")
    _send(
        ctx.w3,
        ctx.user,
        ctx.usdc.functions.approve(ctx.user_vault.address, _DEPOSIT_USDC * 10**6),
    )
    _send(
        ctx.w3,
        ctx.user,
        ctx.user_vault.functions.deposit(
            Web3.to_checksum_address(ctx.addrs["usdc"]), _DEPOSIT_USDC * 10**6
        ),
    )
    _send(
        ctx.w3,
        ctx.user,
        ctx.user_vault.functions.delegateToAllocator(ctx.allocator_vault.address, 86_400),
    )


def step_allocate_all(ctx: Ctx) -> None:
    """Operator allocates `_ALLOC_PER_STRATEGY_USDC` to each of the 6
    strategy vaults. Cohort math (§8.2) needs ≥2 strategies per class
    with non-zero capital — this delivers exactly that."""
    print(f"[4] operator allocate {_ALLOC_PER_STRATEGY_USDC} USDC × 6 strategies")
    for (key, cls), vault in zip(_STRATEGY_VAULT_KEYS, ctx.strategy_vaults, strict=True):
        print(f"    → {key} ({cls})")
        _send(
            ctx.w3,
            ctx.deployer,
            ctx.allocator_vault.functions.allocateToStrategy(
                ctx.user.address,
                vault.address,
                _ALLOC_PER_STRATEGY_USDC * 10**6,
            ),
        )


# ── PR2.A — momentum trade flow ─────────────────────────────


# Two distinct 16-bar series so the resulting `oracle_root` and
# `trade_hash` differ across the two momentum vaults — primary trades
# at bars 0..15 of `scenarios/phase2-multi-class.json::KITE/USDT`
# (the early uptrend leg), variant2 trades at bars 8..23 (still in
# the uptrend but offset). Both ramps satisfy the 1% signal threshold
# trivially.
def _kite_long_series_a() -> list[int]:
    return [int(1.50e18 + i * 5e15) for i in range(16)]  # 1.50 → 1.575


def _kite_long_series_b() -> list[int]:
    return [int(1.55e18 + i * 7e15) for i in range(16)]  # 1.55 → 1.655


def _prove(prover_url: str, strategy_class: str, witness_inputs: dict[str, Any]) -> dict[str, Any]:
    """Synchronous httpx call to the local prover service. snarkjs proof gen
    clocks ~2-10s per proof on dev hardware (mean-reversion is ~2x momentum
    by constraint count); allow 60s."""
    resp = httpx.post(
        f"{prover_url.rstrip('/')}/prove",
        json={"strategyClass": strategy_class, "witnessInputs": witness_inputs},
        timeout=60.0,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"prover {resp.status_code}: {resp.text}")
    return resp.json()


def _anchor_for_vault(ctx: Ctx, vault: Contract, *, kind: str) -> Contract:
    """Resolve the anchor a specific vault was initialized against.

    DeployPhase1 deploys a local OraclePriceAnchor / OracleYieldAnchor
    pair so the Phase-1 stack stays standalone; DeployPhase2 deploys
    its own pair and the deployments-file `oraclePriceAnchor` /
    `oracleYieldAnchor` keys overwrite Phase 1's. The 6 Phase 1 vaults
    are pinned to Phase-1 anchors at init; the 3 Phase-2 variant2
    vaults to Phase-2 anchors. Querying `vault.priceAnchor()` /
    `vault.yieldAnchor()` is the only way to know which is which.
    """
    if kind == "price":
        addr = vault.functions.priceAnchor().call()
    elif kind == "yield":
        addr = vault.functions.yieldAnchor().call()
    else:
        raise ValueError(f"unknown anchor kind: {kind!r}")
    return ctx.w3.eth.contract(address=addr, abi=IOracleAnchor_ABI)


def _commit_proof_oracle_root(
    ctx: Ctx,
    *,
    anchor: Contract,
    domain_name: str,
    root: bytes,
) -> None:
    """Post a single EIP-712-signed commit so a proof's oracle_root /
    yield_oracle_root PI passes `_validateAndVerify`'s `isKnownRoot`
    check. PR1a wired the vault to consult both anchors before the
    Groth16 verifier; the bulk `step_drive_oracle_anchors` cadence
    posts deterministic placeholder roots that don't match what the
    witness actually computes, so each trade-emission step appends a
    one-shot commit for its specific root.

    Window is anchored at the chain's current commit count so we
    always sit strictly after `prev.windowEnd` (the contract's
    monotonicity check). 60s window — generous for a single commit.
    """
    nonce = anchor.functions.nonce().call()
    count = anchor.functions.commitCount().call()
    if count > 0:
        # Strict adjacency to the previous commit so `assert_pr3a_oracle`'s
        # `ws == prev_we` invariant continues to hold across the mix of
        # bulk-cadence and per-proof commits.
        prev_end = int(anchor.functions.commitAt(count - 1).call()[2])
        window_start = prev_end
    else:
        window_start = (
            int(ctx.w3.eth.get_block("latest").get("timestamp", int(time.time()))) * 1_000
        )
    window_end = window_start + 60_000
    domain = {
        "name": domain_name,
        "version": "1",
        "chainId": ctx.chain_id,
        "verifyingContract": Web3.to_checksum_address(anchor.address),
    }
    type_name = "OraclePriceCommit" if "Price" in domain_name else "OracleYieldCommit"
    types = {
        type_name: [
            {"name": "root", "type": "bytes32"},
            {"name": "windowStart", "type": "uint64"},
            {"name": "windowEnd", "type": "uint64"},
            {"name": "nonce", "type": "uint256"},
        ]
    }
    message = {
        "root": root,
        "windowStart": window_start,
        "windowEnd": window_end,
        "nonce": nonce,
    }
    encoded = encode_typed_data(domain_data=domain, message_types=types, message_data=message)
    sig = bytes(ctx.deployer.sign_message(encoded).signature)
    _send(
        ctx.w3,
        ctx.deployer,
        anchor.functions.commit(root, window_start, window_end, sig),
    )


def step_emit_momentum_trades(ctx: Ctx) -> None:
    """Drive a real Groth16 momentum_v1 trade on each of the 2 momentum
    vaults. Per vault:
      1. commitInitialParamsHash with our chosen Poseidon(params) — the
         vaults were registered with placeholder paramsHash values; the
         circuit binds params_hash to the private witness so the manifest
         hash MUST match a real Poseidon-of-params.
      2. Build full witness (oracle_root, trade_hash all computed via
         the canonical Poseidon helper) → POST to prover.
      3. Pack the returned proof into 256-byte calldata; submit to
         StrategyVault.executeWithProof with trades=[] so we don't
         exercise the swap router (PR2 is about the proof path).
    """
    print("\n[5] commitInitialParamsHash + executeWithProof × 2 momentum vaults")
    momentum_vaults: list[tuple[str, Contract, list[int]]] = [
        ("strategyVaultMomentum", ctx.strategy_vaults[0], _kite_long_series_a()),
        ("strategyVaultMomentumVariant2", ctx.strategy_vaults[1], _kite_long_series_b()),
    ]
    for nonce_offset, (key, vault, prices) in enumerate(momentum_vaults):
        print(f"  ── {key} ──")
        # 1. Build witness so we know params_hash to commit.
        block = ctx.w3.eth.block_number
        witness = build_momentum_witness(
            strategy_vault=vault.address,
            allocator_vault=ctx.allocator_vault.address,
            nonce=nonce_offset,
            # Generous window: the e2e mints blocks ~1s apart, momentum proof
            # generation takes a few seconds, so end + 100 is safe.
            block_window_start=block,
            block_window_end=block + 100,
            price_observations_e18=prices,
        )
        # 2. Commit the params hash on-chain. Operator = deployer per Phase 1.
        print(f"    commitInitialParamsHash({witness.params_hash.hex()[:10]}…)")
        _send(
            ctx.w3,
            ctx.deployer,
            ctx.strategy_registry.functions.commitInitialParamsHash(
                vault.address, witness.params_hash
            ),
        )
        # 2b. Commit the proof's oracle_root to *this vault's* price
        # anchor so `_validateAndVerify`'s PR1a `isKnownRoot` check
        # passes. Phase-1 and Phase-2 vaults have distinct anchor pairs
        # (see `_anchor_for_vault`).
        print(f"    OraclePriceAnchor.commit({witness.oracle_root.hex()[:10]}…)")
        _commit_proof_oracle_root(
            ctx,
            anchor=_anchor_for_vault(ctx, vault, kind="price"),
            domain_name="HeliosOraclePriceAnchor",
            root=witness.oracle_root,
        )
        # 3. Generate proof.
        print("    proving (snarkjs.fullProve)…")
        result = _prove(ctx.prover_url, "momentum_v1", witness.inputs)
        proof_bytes = proof_to_bytes(result["proof"])
        public_inputs = public_signals_to_uints(result["publicSignals"])
        if len(proof_bytes) != 256:
            raise RuntimeError(f"proof bytes length {len(proof_bytes)} != 256")
        # 4. Submit on-chain. trades=[] so no swap is performed; the
        #    StrategyVault still verifies the proof + emits TradeAttested.
        print("    executeWithProof → expect TradeAttested")
        _send(
            ctx.w3,
            ctx.deployer,
            vault.functions.executeWithProof(proof_bytes, public_inputs, []),
        )


# ── PR2.B — mean-reversion trade flow ──────────────────────


# Two distinct 16-bar series satisfying the n-sigma long-entry rule:
# 15 bars at one price, last bar at a deep dip well below the
# 16-bar mean. Different magnitudes → different oracle_root +
# trade_hash across the two vaults.
def _meanrev_long_series_a() -> list[int]:
    return [int(1.00e21)] * 15 + [int(0.70e21)]  # 30% dip on bar 15


def _meanrev_long_series_b() -> list[int]:
    return [int(1.20e21)] * 15 + [int(0.84e21)]  # same ratio, shifted


def step_emit_mean_reversion_trades(ctx: Ctx) -> None:
    """Drive a real Groth16 mean_reversion_v1 trade on each of the 2
    mean-rev vaults. Same shape as the momentum step but the witness
    builder enforces the n-sigma entry constraint instead of the
    momentum delta one. `signal_threshold` slot is reused as
    `n_sigma_x100` (200 ⇒ 2.00σ).
    """
    print("\n[6] commitInitialParamsHash + executeWithProof × 2 mean-reversion vaults")
    mr_vaults: list[tuple[str, Contract, list[int]]] = [
        ("strategyVaultMeanReversion", ctx.strategy_vaults[2], _meanrev_long_series_a()),
        ("strategyVaultMeanReversionVariant2", ctx.strategy_vaults[3], _meanrev_long_series_b()),
    ]
    for nonce_offset, (key, vault, prices) in enumerate(mr_vaults):
        print(f"  ── {key} ──")
        block = ctx.w3.eth.block_number
        witness = build_mean_reversion_witness(
            strategy_vault=vault.address,
            allocator_vault=ctx.allocator_vault.address,
            nonce=nonce_offset,
            block_window_start=block,
            block_window_end=block + 100,
            price_observations=prices,
        )
        print(f"    commitInitialParamsHash({witness.params_hash.hex()[:10]}…)")
        _send(
            ctx.w3,
            ctx.deployer,
            ctx.strategy_registry.functions.commitInitialParamsHash(
                vault.address, witness.params_hash
            ),
        )
        print(f"    OraclePriceAnchor.commit({witness.oracle_root.hex()[:10]}…)")
        _commit_proof_oracle_root(
            ctx,
            anchor=_anchor_for_vault(ctx, vault, kind="price"),
            domain_name="HeliosOraclePriceAnchor",
            root=witness.oracle_root,
        )
        print("    proving (snarkjs.fullProve)…")
        result = _prove(ctx.prover_url, "mean_reversion_v1", witness.inputs)
        proof_bytes = proof_to_bytes(result["proof"])
        public_inputs = public_signals_to_uints(result["publicSignals"])
        if len(proof_bytes) != 256:
            raise RuntimeError(f"proof bytes length {len(proof_bytes)} != 256")
        print("    executeWithProof → expect TradeAttested")
        _send(
            ctx.w3,
            ctx.deployer,
            vault.functions.executeWithProof(proof_bytes, public_inputs, []),
        )


# ── PR2.C — yield-rotation trade flow ─────────────────────


def step_emit_yield_rotation_trades(ctx: Ctx) -> None:
    """Drive a real Groth16 yield_rotation_v1 rotation on each of the 2
    YR vaults. Distinct from momentum/mean-rev:

      - 12 public inputs (PR2 promoted strategy_vault, params_hash,
        markets_allowlist_root from private witnesses to PIs).
      - Witness includes Poseidon Merkle inclusion proofs against both
        a 64-leaf yield-oracle tree and a 16-leaf allowlist tree —
        constructed in `_phase2_witness::build_yield_rotation_witness`
        with the same 4-market test cosmos as `gen-fixture-yr.js`
        (AAVE_USDC / COMPOUND_USDC / AAVE_USDT / COMPOUND_USDT).
      - On-chain entry point is `executeYieldRotationWithProof`, not
        `executeWithProof`.
      - Per-vault `commitInitialParamsHash(Poseidon(threshold, bridging))`
        before the proof — same flow as momentum / mean-rev. Without
        this the vault's `_activeParamsHash()` returns zero and the
        proof's `params_hash` PI doesn't match.
      - One-shot `setMarketAllowlistRoot(CLASS_YR, allow_root)` before
        the first proof so the registry's per-class root matches the
        PI built from the canonical 4-market test cosmos.

    Primary rotates AAVE_USDC → COMPOUND_USDC (130bps differential);
    variant2 rotates AAVE_USDT → COMPOUND_USDT (120bps). Both clear
    the threshold + bridging cost (110 bps).
    """
    print("\n[7] executeYieldRotationWithProof × 2 yield-rotation vaults")
    yr_vaults: list[tuple[str, Contract, str, str]] = [
        ("strategyVaultYieldRotation", ctx.strategy_vaults[4], "AAVE_USDC", "COMPOUND_USDC"),
        (
            "strategyVaultYieldRotationVariant2",
            ctx.strategy_vaults[5],
            "AAVE_USDT",
            "COMPOUND_USDT",
        ),
    ]
    # Seed the registry's allowlist root from the canonical 4-market
    # cosmos. Owner is the deployer (set in DeployPhase1.s.sol).
    seed_witness = build_yield_rotation_witness(
        strategy_vault=yr_vaults[0][1].address,
        allocator_vault=ctx.allocator_vault.address,
        nonce=0,
        block_window_end=ctx.w3.eth.block_number + 100,
    )
    allowlist_root_bytes = seed_witness.markets_allowlist_root.to_bytes(32, "big")
    print(f"    setMarketAllowlistRoot(YR, {allowlist_root_bytes.hex()[:10]}…)")
    _send(
        ctx.w3,
        ctx.deployer,
        ctx.strategy_registry.functions.setMarketAllowlistRoot(
            CLASS_YR_BYTES32, allowlist_root_bytes
        ),
    )

    for nonce_offset, (key, vault, from_m, to_m) in enumerate(yr_vaults):
        print(f"  ── {key} ({from_m} → {to_m}) ──")
        block = ctx.w3.eth.block_number
        witness = build_yield_rotation_witness(
            strategy_vault=vault.address,
            allocator_vault=ctx.allocator_vault.address,
            nonce=nonce_offset,
            block_window_end=block + 100,
            from_market=from_m,
            to_market=to_m,
        )
        print(f"    commitInitialParamsHash({witness.params_hash.hex()[:10]}…)")
        _send(
            ctx.w3,
            ctx.deployer,
            ctx.strategy_registry.functions.commitInitialParamsHash(
                vault.address, witness.params_hash
            ),
        )
        yield_root_bytes = witness.yield_oracle_root.to_bytes(32, "big")
        print(f"    OracleYieldAnchor.commit({yield_root_bytes.hex()[:10]}…)")
        _commit_proof_oracle_root(
            ctx,
            anchor=_anchor_for_vault(ctx, vault, kind="yield"),
            domain_name="HeliosOracleYieldAnchor",
            root=yield_root_bytes,
        )
        print("    proving (snarkjs.fullProve)…")
        result = _prove(ctx.prover_url, "yield_rotation_v1", witness.inputs)
        proof_bytes = proof_to_bytes(result["proof"])
        public_inputs = public_signals_to_uints(result["publicSignals"])
        if len(proof_bytes) != 256:
            raise RuntimeError(f"proof bytes length {len(proof_bytes)} != 256")
        print("    executeYieldRotationWithProof → expect YieldRotationAttested")
        _send(
            ctx.w3,
            ctx.deployer,
            vault.functions.executeYieldRotationWithProof(proof_bytes, public_inputs, []),
        )


# ── PR3.A — oracle anchor cadence + NAV trajectories ──────


def step_drive_oracle_anchors(ctx: Ctx) -> dict[str, int]:
    """Post `ANCHOR_COMMITS_PER_ANCHOR` price + yield commits to the
    deployed oracle anchors. Each commit covers a `10-bar` slice of the
    90d / 200-bar window. Roots are deterministic non-zero placeholders;
    the contracts only check signature recovery + window monotonicity.

    Returns a `{kind: count}` summary used by `assert_pr3a_oracle`.
    """
    print(
        f"\n[8] OraclePriceAnchor + OracleYieldAnchor commits "
        f"× {ANCHOR_COMMITS_PER_ANCHOR} each (1 per 10 bars)"
    )
    base_ts_sec = ctx.synthetic_now_sec - 90 * DAY_SEC
    driver = OracleAnchorDriver(
        w3=ctx.w3,
        chain_id=ctx.chain_id,
        signer_pk=_OPERATOR_PK,
        price_anchor=ctx.oracle_price_anchor,
        yield_anchor=ctx.oracle_yield_anchor,
        base_ts_sec=base_ts_sec,
    )
    price_receipts, yield_receipts = driver.drive(_send, ctx.deployer)
    print(
        f"  ✓ price commits posted: {len(price_receipts)}; "
        f"yield commits posted: {len(yield_receipts)}"
    )
    return {"price": len(price_receipts), "yield": len(yield_receipts)}


def step_drive_nav_trajectories(ctx: Ctx) -> dict[str, int]:
    """Post `NAV_SAMPLES_PER_VAULT` daily NAV updates per vault, oldest
    first. Trajectories diverge across vaults by design — see
    `_phase2_oracle_nav.trajectory_for` for the signal map. The output
    is an input to PR3.B's reputation engine drive (cohort math
    consumes the resulting NAVReported event stream).
    """
    print(f"\n[9] reportNAV × {NAV_SAMPLES_PER_VAULT} samples × 6 vaults (daily cadence)")
    vaults_by_role = {
        key: vault
        for (key, _cls), vault in zip(_STRATEGY_VAULT_KEYS, ctx.strategy_vaults, strict=True)
    }
    driver = NavTrajectoryDriver(
        w3=ctx.w3,
        chain_id=ctx.chain_id,
        signer_pk=_OPERATOR_PK,
        synthetic_now_sec=ctx.synthetic_now_sec,
    )
    receipts = driver.drive(_send, ctx.deployer, vaults_by_role)
    counts = {role: len(rs) for role, rs in receipts.items()}
    for role, n in counts.items():
        print(f"  ✓ {role}: {n} NAV updates")
    return counts


# ── Assertions ───────────────────────────────────────────────


def _logs(contract: Contract, event_name: str, from_block: int) -> list[Any]:
    event = getattr(contract.events, event_name)
    return list(event.get_logs(from_block=from_block, to_block="latest"))


def assert_pr1_skeleton(ctx: Ctx, start_block: int) -> None:
    print("\n=== PR1 skeleton assertions ===")
    alloc_created = _logs(ctx.allocator_vault, "AllocationCreated", start_block)

    # Filter to allocations for our user — Phase 1 e2e may have left
    # state on the same anvil if SKIP_ANVIL_BOOT was used.
    user_addr = ctx.user.address.lower()
    our_allocs = [e for e in alloc_created if e["args"]["user"].lower() == user_addr]
    assert len(our_allocs) == 6, (
        f"expected exactly 6 AllocationCreated for user, got {len(our_allocs)} "
        f"(total events: {len(alloc_created)})"
    )

    # Each strategy vault must appear exactly once in the user's allocations.
    expected_vaults = {ctx.addrs[k].lower() for (k, _cls) in _STRATEGY_VAULT_KEYS}
    seen_vaults = {e["args"]["strategy"].lower() for e in our_allocs}
    assert seen_vaults == expected_vaults, (
        f"allocation set mismatch:\n  expected={expected_vaults}\n  got={seen_vaults}"
    )

    print(f"  ✓ AllocationCreated x{len(our_allocs)} (one per strategy)")
    print("  ✓ all 6 strategies (2× per class) received non-zero capital")
    print("\nPR1 skeleton: deploy + meta-strategy + 6-way allocation GREEN")


def assert_pr2a_momentum_trades(ctx: Ctx, start_block: int) -> None:
    """One TradeAttested event per momentum vault, going through the
    real MomentumV1Verifier (DeployPhase2 swapped in the real adapters).
    Cohort completeness for momentum_v1 is satisfied — this is the
    first time a real Groth16 proof has landed for any class in repo
    history.
    """
    print("\n=== PR2.A momentum-class assertions ===")
    primary, variant2 = ctx.strategy_vaults[0], ctx.strategy_vaults[1]
    primary_logs = _logs(primary, "TradeAttested", start_block)
    variant2_logs = _logs(variant2, "TradeAttested", start_block)
    assert len(primary_logs) >= 1, (
        f"expected ≥1 TradeAttested on {primary.address} (primary momentum), got 0"
    )
    assert len(variant2_logs) >= 1, (
        f"expected ≥1 TradeAttested on {variant2.address} (variant2 momentum), got 0"
    )
    primary_hash = primary_logs[0]["args"]["tradeHash"]
    variant2_hash = variant2_logs[0]["args"]["tradeHash"]
    assert primary_hash != variant2_hash, "trade_hashes collided across vaults"
    print(f"  ✓ TradeAttested on primary    {primary.address} (hash={primary_hash.hex()[:10]}…)")
    print(f"  ✓ TradeAttested on variant2   {variant2.address} (hash={variant2_hash.hex()[:10]}…)")
    print("\nPR2.A: real-proof momentum flow GREEN")


def assert_pr2b_mean_reversion_trades(ctx: Ctx, start_block: int) -> None:
    """One TradeAttested event per mean-reversion vault, going through the
    real MeanReversionV1Verifier."""
    print("\n=== PR2.B mean-reversion-class assertions ===")
    primary, variant2 = ctx.strategy_vaults[2], ctx.strategy_vaults[3]
    primary_logs = _logs(primary, "TradeAttested", start_block)
    variant2_logs = _logs(variant2, "TradeAttested", start_block)
    assert len(primary_logs) >= 1, (
        f"expected ≥1 TradeAttested on {primary.address} (primary mean-rev), got 0"
    )
    assert len(variant2_logs) >= 1, (
        f"expected ≥1 TradeAttested on {variant2.address} (variant2 mean-rev), got 0"
    )
    primary_hash = primary_logs[0]["args"]["tradeHash"]
    variant2_hash = variant2_logs[0]["args"]["tradeHash"]
    assert primary_hash != variant2_hash, "trade_hashes collided across vaults"
    print(f"  ✓ TradeAttested on primary    {primary.address} (hash={primary_hash.hex()[:10]}…)")
    print(f"  ✓ TradeAttested on variant2   {variant2.address} (hash={variant2_hash.hex()[:10]}…)")
    print("\nPR2.B: real-proof mean-reversion flow GREEN")


def assert_pr2c_yield_rotation_trades(ctx: Ctx, start_block: int) -> None:
    """One YieldRotationAttested event per YR vault, going through the
    real YieldRotationV1Verifier. Distinct event from TradeAttested —
    YR has no asset-pair / amount-out semantics, the on-chain emit
    carries (m_from, m_to, amount_rotating, yield_oracle_root)."""
    print("\n=== PR2.C yield-rotation-class assertions ===")
    primary, variant2 = ctx.strategy_vaults[4], ctx.strategy_vaults[5]
    primary_logs = _logs(primary, "YieldRotationAttested", start_block)
    variant2_logs = _logs(variant2, "YieldRotationAttested", start_block)
    assert len(primary_logs) >= 1, (
        f"expected ≥1 YieldRotationAttested on {primary.address} (primary YR), got 0"
    )
    assert len(variant2_logs) >= 1, (
        f"expected ≥1 YieldRotationAttested on {variant2.address} (variant2 YR), got 0"
    )
    primary_hash = primary_logs[0]["args"]["tradeHash"]
    variant2_hash = variant2_logs[0]["args"]["tradeHash"]
    primary_from = primary_logs[0]["args"]["mFrom"]
    primary_to = primary_logs[0]["args"]["mTo"]
    variant2_from = variant2_logs[0]["args"]["mFrom"]
    variant2_to = variant2_logs[0]["args"]["mTo"]
    assert primary_hash != variant2_hash, "YR trade_hashes collided across vaults"
    assert (primary_from, primary_to) == (1, 2), (
        f"primary rotation expected AAVE_USDC(1) → COMPOUND_USDC(2), "
        f"got {primary_from} → {primary_to}"
    )
    assert (variant2_from, variant2_to) == (3, 4), (
        f"variant2 rotation expected AAVE_USDT(3) → COMPOUND_USDT(4), "
        f"got {variant2_from} → {variant2_to}"
    )
    print(
        f"  ✓ YieldRotationAttested on primary  {primary.address} "
        f"(mkt {primary_from}→{primary_to}, hash={primary_hash.hex()[:10]}…)"
    )
    print(
        f"  ✓ YieldRotationAttested on variant2 {variant2.address} "
        f"(mkt {variant2_from}→{variant2_to}, hash={variant2_hash.hex()[:10]}…)"
    )
    print("\nPR2.C: real-proof yield-rotation flow GREEN")


# ── PR3.B — drive reputation engine + §8.2 assertions ─────


def step_drive_reputation(ctx: Ctx, start_block: int) -> dict[str, EngineUpdate]:
    """Run `ReputationEngine.tick_once()` against the local on-chain stub.

    Pins `now_unix` to `synthetic_now_sec` so the 90d slice covers the
    NAV trajectories planted by `step_drive_nav_trajectories`. Returns
    `{strategy_id_lower: EngineUpdate}` for downstream assertions.
    """
    print("\n[10] reputation.engine.tick_once (90d slice → §8.2 score)")

    stub = LocalGoldskyStub(
        w3=ctx.w3,
        registry=ctx.strategy_registry,
        allocator_vault=ctx.allocator_vault,
        strategy_vaults=ctx.strategy_vaults,
        from_block=start_block,
    )
    # Signer is only used to wrap the score in a SignedUpdate envelope —
    # the e2e doesn't post on-chain, so the signer pk and anchor address
    # exist only to satisfy the signer constructor. Use the deployer key
    # and the deployed ReputationAnchorV2 address so the typehash
    # produces a v1-shaped signature consistent with the shadow-mode
    # default (`REPUTATION_TYPEHASH_VERSION=1`).
    signer = ReputationSigner(
        _OPERATOR_PK,
        chain_id=ctx.chain_id,
        anchor_address=Web3.to_checksum_address(ctx.addrs["reputationAnchorV2"]),
    )
    engine = ReputationEngine(stub, signer, poll_interval_sec=60)  # type: ignore[arg-type]
    updates = asyncio.run(engine.tick_once(now_unix=ctx.synthetic_now_sec))
    by_id = {u.state.strategy_id.lower(): u for u in updates}
    print(f"  ✓ engine.tick_once produced {len(updates)} updates")
    for (key, _cls), vault in zip(_STRATEGY_VAULT_KEYS, ctx.strategy_vaults, strict=True):
        u = by_id[vault.address.lower()]
        c = u.outputs.components
        print(
            f"    {key}: score={u.outputs.score_e4:>+6} "
            f"perf={c.performance:+.3f} risk={c.risk:.3f} "
            f"proof={c.proof:.3f} stake={c.stake:.3f} age={c.age:.3f}"
        )
    return by_id


# ── PR3.5 — WS7.A params rotation in scenario ─────────────


def step_rotate_params_for_strategy(ctx: Ctx, vault_role: str = "strategyVaultMomentum") -> bytes:
    """WS7.A: drive `initiateParamsRotation` → fast-forward past
    `stakeCooldown` (7 days per `DeployPhase1.STAKE_COOLDOWN`) →
    `completeParamsRotation`. Operator-only; uses the deployer key
    which doubles as the strategy operator in Phase 1/2 scaffolding.

    The rotation is on `vault_role` only — the other 5 vaults keep
    their pre-rotation track record so PR3.B's cohort assertions
    still pass alongside PR3.5's reset assertion.
    """
    print(f"\n[11] WS7.A: rotateParams for {vault_role}")
    vault_addr = ctx.addrs[vault_role]
    new_params = keccak(b"helios.ws7a.e2e.rotated-params")

    print(f"  initiateParamsRotation({vault_addr[:10]}…, new_hash={new_params.hex()[:10]}…)")
    _send(
        ctx.w3,
        ctx.deployer,
        ctx.strategy_registry.functions.initiateParamsRotation(
            Web3.to_checksum_address(vault_addr), new_params
        ),
    )

    # Fast-forward past `stakeCooldown` via anvil's evm_increaseTime +
    # evm_mine (the Foundry-flavored namespace works on anvil too).
    # Cooldown is hardcoded to 7 days per `DeployPhase1.STAKE_COOLDOWN`;
    # the StrategyRegistry interface ABI doesn't expose the immutable
    # getter, so we don't read it back from chain.
    # `last_rotation_epoch` will land in the FUTURE relative to wall-clock
    # `synthetic_now_sec` — that's exactly what we want, because then ALL
    # pre-rotation NAVs/trades fall behind the new epoch and the engine
    # filters them out, collapsing the rotated vault to the cold-start
    # path (W_STAKE × stake floor per `compute_score`'s WS7.B branch).
    cooldown_sec = 7 * 24 * 60 * 60
    print(f"  evm_increaseTime({cooldown_sec + 60}) + evm_mine")
    ctx.w3.provider.make_request("evm_increaseTime", [cooldown_sec + 60])  # type: ignore[union-attr]
    ctx.w3.provider.make_request("evm_mine", [])  # type: ignore[union-attr]

    print("  completeParamsRotation → expect ParamsRotated event")
    _send(
        ctx.w3,
        ctx.deployer,
        ctx.strategy_registry.functions.completeParamsRotation(
            Web3.to_checksum_address(vault_addr)
        ),
    )
    return new_params


# ── PR3.5.C — WS7.B sentinel bootstrap-pool drive ─────────


def step_drive_bootstrap_pool(
    ctx: Ctx,
    rep_updates: dict[str, EngineUpdate],
) -> dict[str, Any]:
    """WS7.B: drive `SentinelAllocator.allocate(...)` over the 7-vault
    cohort (6 trading vaults + 1 fresh strategy registered after the
    deploy pipeline). Asserts the fresh vault — `trades_attested = 0`,
    `reputation_score = 0` — receives non-zero capital from the
    bootstrap pool while every trading vault is graduated.

    Capital is sized so the bootstrap split (10% default) ≥ 1 wei of
    USDC: with 60k delegated × 1000 bps = 6k USDC of cold-start capital
    spread across the cold-start cohort.

    The user's `min_attested_trades` is set to 50 (default per the
    allocator-sdk MetaStrategy). Each Phase 2 trading vault has 1
    attested trade by this point, so they're STILL inside the cold-
    start gate. To keep the test focused on the fresh-vault bootstrap
    path we override `min_attested_trades = 1` so 6 trading vaults
    are graduated and only the fresh vault qualifies. (Helios.md §8.7
    leaves `min_attested_trades` as a per-user knob.)
    """
    print("\n[12] WS7.B: SentinelAllocator.allocate (bootstrap-pool drive)")

    # Lazy import — keeps the e2e parsable even when the workspace
    # didn't install helios-allocator-sdk / helios-sentinel.
    from helios_allocator.types import MetaStrategy, StrategyCandidate
    from sentinel.allocator import SentinelAllocator

    fresh_addr = ctx.addrs.get(_FRESH_STRATEGY_KEY)
    if fresh_addr is None:
        raise RuntimeError(
            f"deployments file missing {_FRESH_STRATEGY_KEY!r}; "
            "did RegisterFreshStrategy.s.sol run?"
        )

    candidates: list[Any] = []
    # 6 trading vaults — populate `trades_attested` and reputation
    # score from the post-rotation engine snapshot.
    for (key, cls), vault in zip(_STRATEGY_VAULT_KEYS, ctx.strategy_vaults, strict=True):
        sid = vault.address.lower()
        u = rep_updates[sid]
        candidates.append(
            StrategyCandidate(
                strategy_id=vault.address,
                declared_class=cls,
                chain_id=ctx.chain_id,
                operator=ctx.deployer.address,
                fee_rate_bps=1000 if "Variant2" not in key else 1500,
                stake_amount_usd=5_000,
                max_capacity_usd=1_000_000,
                current_allocations_usd=_ALLOC_PER_STRATEGY_USDC,
                reputation_score=max(0.0, u.outputs.score_e4 / 10_000),
                trades_attested=u.state.trades_attested,
            )
        )
    # Fresh vault — zero track record, full capacity, fresh stake.
    candidates.append(
        StrategyCandidate(
            strategy_id=fresh_addr,
            declared_class=_FRESH_STRATEGY_CLASS,
            chain_id=ctx.chain_id,
            operator=ctx.deployer.address,
            fee_rate_bps=1500,
            stake_amount_usd=5_000,
            max_capacity_usd=1_000_000,
            current_allocations_usd=0,
            reputation_score=0.0,
            trades_attested=0,
        )
    )

    meta = MetaStrategy(
        user_address=ctx.user.address,
        allowed_strategy_classes=["momentum_v1", "mean_reversion_v1", "yield_rotation_v1"],
        allowed_assets=[ctx.addrs["usdc"]],
        allowed_chains=[ctx.chain_id],
        max_capital_usd=_DEPOSIT_USDC,
        max_per_strategy_bps=5_000,
        max_strategies_count=10,
        drawdown_threshold_bps=2_000,
        max_fee_rate_bps=2_500,
        rebalance_cadence_sec=3_600,
        valid_until=0,
        bootstrap_share_bps=1_000,  # 10% — default
        min_attested_trades=1,  # graduate the 6 trading vaults
    )
    targets = SentinelAllocator().allocate(meta, candidates, capital=_DEPOSIT_USDC)
    by_id = {t.strategy_id.lower(): t for t in targets}
    print(f"  ✓ allocator.allocate produced {len(targets)} targets")
    for t in targets:
        print(f"    {t.strategy_id[:10]}…  ${t.capital_usd:>6}  ({t.weight_bps} bps)")
    return {"targets_by_id": by_id, "fresh_addr": fresh_addr}


def assert_pr3_5c_bootstrap_pool(
    ctx: Ctx,
    bootstrap_result: dict[str, Any],
) -> None:
    """Verify the WS7.B bootstrap pool actually allocates cold-start
    capital to the fresh strategy:

      1. The fresh vault appears in the allocation targets list.
      2. Its allocated capital is > 0 — the bootstrap pool reserved
         10% of the user's delegated capital for cold-start strategies,
         and only the fresh vault qualifies (`trades_attested = 0 <
         min_attested_trades = 1`).
      3. Its weight_bps is bounded by `max_per_strategy_bps` (defensive).
      4. The 6 trading vaults DO NOT receive bootstrap capital — they
         are graduated (trades_attested ≥ min_attested_trades), so
         their entire allocation comes from the main pool's rank
         function. We can't easily separate the two pools post-merge,
         but we CAN verify the fresh vault's capital == bootstrap pool
         capital (since it's the only cold-start candidate).
    """
    print("\n=== PR3.5.C WS7.B bootstrap-pool assertions ===")
    by_id: dict[str, Any] = bootstrap_result["targets_by_id"]
    fresh_addr_lower: str = bootstrap_result["fresh_addr"].lower()

    # 1. Fresh vault is in the result.
    assert fresh_addr_lower in by_id, (
        f"fresh strategy {fresh_addr_lower} missing from allocator output; got {list(by_id)}"
    )
    fresh_target = by_id[fresh_addr_lower]

    # 2. Non-zero capital.
    assert fresh_target.capital_usd > 0, (
        f"fresh strategy received zero capital from bootstrap pool; target={fresh_target}"
    )
    print(
        f"  ✓ fresh strategy {fresh_addr_lower[:10]}… got "
        f"${fresh_target.capital_usd} ({fresh_target.weight_bps} bps)"
    )

    # 3. Per-strategy cap respected.
    assert fresh_target.weight_bps <= 5_000, (
        f"fresh strategy weight {fresh_target.weight_bps} bps exceeds max_per_strategy_bps=5000"
    )
    print(f"  ✓ weight_bps={fresh_target.weight_bps} respects max_per_strategy_bps=5000")

    # 4. Bootstrap-pool budget = 10% of total delegated = $6000. With
    # max_per_strategy_bps=5000 (50%) and only ONE cold-start candidate,
    # the SDK's `score_weighted_allocation` caps the single recipient at
    # half the SUB-POOL budget = $3000. The other $3000 of unused
    # bootstrap budget falls back to the main pool (see
    # `SentinelAllocator.allocate` line 60-61). So a fresh vault as
    # the sole cold-start eligible should receive AT LEAST half the
    # 10% bootstrap reserve.
    bootstrap_budget = (_DEPOSIT_USDC * 1_000) // 10_000
    sub_pool_cap = (bootstrap_budget * 5_000) // 10_000  # max_per_strategy_bps
    assert fresh_target.capital_usd >= sub_pool_cap, (
        f"fresh strategy capital ${fresh_target.capital_usd} is below the "
        f"per-strategy cap inside the bootstrap pool (${sub_pool_cap}); "
        f"bootstrap pool may not be allocating fully — bootstrap_budget="
        f"${bootstrap_budget}, max_per_strategy_bps=5000"
    )
    print(
        f"  ✓ bootstrap pool funneled ${fresh_target.capital_usd} to the "
        f"fresh vault (= sub-pool cap of bootstrap budget ${bootstrap_budget})"
    )

    print("\nPR3.5.C: WS7.B sentinel bootstrap pool GREEN")


def assert_pr3_5_rotation_reset(
    ctx: Ctx,
    pre_updates: dict[str, EngineUpdate],
    post_updates: dict[str, EngineUpdate],
    rotated_role: str = "strategyVaultMomentum",
) -> None:
    """Verify the rotation re-tick produces the expected reset:

    1. The rotated vault's `last_rotation_epoch` is now > 0 (fetched
       by LocalGoldskyStub from the on-chain ParamsRotated event).
    2. Its post-rotation `trades_attested` (the engine input) drops
       to 0 — every pre-rotation trade timestamp is < rotation epoch.
    3. Its post-rotation score collapses to the WS7.B cold-start
       floor: `W_STAKE × stake_normalized` ≈ 1000 (e4) since stake
       is at the cohort cap.
    4. Risk + drawdown components are PRESERVED across the rotation —
       the rotated vault's `max_drawdown_bps_90d` does not change
       (rotation cannot mask prior drawdown history).
    5. The 5 non-rotated vaults' scores are UNCHANGED across the
       re-tick (their `last_rotation_epoch` is still 0).
    """
    print("\n=== PR3.5 WS7.A rotation-reset assertions ===")

    rotated_lower = ctx.addrs[rotated_role].lower()
    pre = pre_updates[rotated_lower]
    post = post_updates[rotated_lower]

    # 1 & 2. Rotation epoch + post-rotation trades_attested = 0.
    assert post.state.last_rotation_epoch > 0, (
        f"{rotated_role}: post-tick state should carry a non-zero "
        f"last_rotation_epoch from ParamsRotated; got "
        f"{post.state.last_rotation_epoch}"
    )
    assert post.inputs.trades_attested == 0, (
        f"{rotated_role}: post-rotation trades_attested should be 0; "
        f"got {post.inputs.trades_attested}"
    )
    print(
        f"  ✓ {rotated_role}: rotation_epoch={post.state.last_rotation_epoch} "
        f"(pre-rotation trades filtered out)"
    )

    # 3. Score collapses to cold-start floor (W_STAKE × stake).
    # With stake at cohort max, stake_norm = 1.0 → floor = 0.10 → e4 = 1000.
    expected_floor_e4 = round(0.10 * post.outputs.components.stake * 10_000)
    assert abs(post.outputs.score_e4 - expected_floor_e4) <= 1, (
        f"{rotated_role}: post-rotation score {post.outputs.score_e4} "
        f"should land at cold-start floor ≈ {expected_floor_e4} "
        f"(W_STAKE × stake_norm={post.outputs.components.stake})"
    )
    assert post.outputs.score_e4 < pre.outputs.score_e4, (
        f"{rotated_role}: rotation must depress score; "
        f"pre={pre.outputs.score_e4} post={post.outputs.score_e4}"
    )
    print(
        f"  ✓ {rotated_role}: score collapsed pre={pre.outputs.score_e4} → "
        f"post={post.outputs.score_e4} (cold-start floor)"
    )

    # 4. Drawdown preserved — rotation cannot wipe risk history.
    assert post.inputs.max_drawdown_bps_90d == pre.inputs.max_drawdown_bps_90d, (
        f"{rotated_role}: rotation must NOT reset max_drawdown_bps_90d; "
        f"pre={pre.inputs.max_drawdown_bps_90d} post={post.inputs.max_drawdown_bps_90d}"
    )
    print(
        f"  ✓ {rotated_role}: max_drawdown_bps_90d preserved "
        f"({post.inputs.max_drawdown_bps_90d} bps)"
    )

    # 5. Non-rotated vaults: scores unchanged across the re-tick.
    for key, _cls in _STRATEGY_VAULT_KEYS:
        if key == rotated_role:
            continue
        sid = ctx.addrs[key].lower()
        assert pre_updates[sid].outputs.score_e4 == post_updates[sid].outputs.score_e4, (
            f"{key}: non-rotated vault's score changed across re-tick "
            f"({pre_updates[sid].outputs.score_e4} → "
            f"{post_updates[sid].outputs.score_e4}); only rotated vault should reset"
        )
    print("  ✓ 5 non-rotated vaults: scores unchanged across re-tick")
    print("\nPR3.5: WS7.A params-rotation reset GREEN")


# ── PR3.B — drive reputation engine + §8.2 assertions ─────


def assert_pr3b_reputation_822(
    ctx: Ctx,
    updates_by_id: dict[str, EngineUpdate],
) -> None:
    """Full §8.2 assertions on the engine output:

    1. All 6 strategies received a score and a signed update envelope.
    2. ScoreComponents has all 5 sub-components populated with the
       expected sign / range (perf ∈ [-1,1], others ∈ [0,1]).
    3. Cohort stats are reported per class for each window — even when
       in the documented `is_fallback=True` mode (cohort_size=2 <
       MIN_COHORT_SIZE=3 per WS7.B).
    4. Within-class divergence: the primary strategy of each class
       must score strictly higher than its variant2 sibling.
    5. Drawdown ranking: momentum_v1 variant2 (heavy 28% drawdown)
       must have a strictly LOWER `risk` component than its primary
       (no drawdown).
    6. componentsHash is a 32-byte non-empty value (typehash v2 input).
    """
    print("\n=== PR3.B reputation §8.2 assertions ===")

    # 1. Update completeness.
    expected_ids = {ctx.addrs[k].lower() for (k, _cls) in _STRATEGY_VAULT_KEYS}
    seen_ids = set(updates_by_id.keys())
    assert seen_ids == expected_ids, (
        f"engine update set mismatch:\n  expected={expected_ids}\n  got={seen_ids}"
    )
    print(f"  ✓ engine produced 1 update per vault ({len(seen_ids)} total)")

    # 2. Component shape + range checks per update.
    for sid, u in updates_by_id.items():
        c = u.outputs.components
        assert -1.0 <= c.performance <= 1.0, f"{sid}: perf out of range: {c.performance}"
        assert 0.0 <= c.risk <= 1.0, f"{sid}: risk out of range: {c.risk}"
        assert 0.0 <= c.proof <= 1.0, f"{sid}: proof out of range: {c.proof}"
        assert 0.0 <= c.stake <= 1.0, f"{sid}: stake out of range: {c.stake}"
        assert 0.0 <= c.age <= 1.0, f"{sid}: age out of range: {c.age}"
        assert u.outputs.components_hash and len(u.outputs.components_hash) == 32, (
            f"{sid}: componentsHash missing or wrong length"
        )
        assert u.signed.update.actor_type == ActorType.STRATEGY
    print("  ✓ all 5 §8.2 components populated within range; componentsHash present")

    # 3. Cohort stats per class per window.
    classes_seen: set[str] = set()
    for u in updates_by_id.values():
        cls = u.state.declared_class
        classes_seen.add(cls)
        for window_name, stats in (
            ("7d", u.cohort.win_7d),
            ("30d", u.cohort.win_30d),
            ("90d", u.cohort.win_90d),
        ):
            assert stats.size == 2, (
                f"{cls}/{window_name}: expected cohort_size=2 (we registered 2 "
                f"strategies per class), got {stats.size}"
            )
            # WS7.B documents the n=2 cohort as fallback (median=0, iqr=1).
            assert stats.is_fallback is True, (
                f"{cls}/{window_name}: cohort with n=2 should be is_fallback=True per WS7.B"
            )
    assert len(classes_seen) == 3, (
        f"expected 3 distinct declared_classes (mom/mr/yr), got {len(classes_seen)}"
    )
    print("  ✓ cohort stats reported per class per window (n=2 → fallback per WS7.B)")

    # 4. Within-class divergence: primary > variant2.
    pairs = (
        ("strategyVaultMomentum", "strategyVaultMomentumVariant2", "momentum"),
        ("strategyVaultMeanReversion", "strategyVaultMeanReversionVariant2", "mean-rev"),
        ("strategyVaultYieldRotation", "strategyVaultYieldRotationVariant2", "yield-rot"),
    )
    for primary_key, variant2_key, label in pairs:
        primary = updates_by_id[ctx.addrs[primary_key].lower()]
        variant2 = updates_by_id[ctx.addrs[variant2_key].lower()]
        assert primary.outputs.score_e4 > variant2.outputs.score_e4, (
            f"{label}: primary must outscore variant2 — "
            f"primary={primary.outputs.score_e4} variant2={variant2.outputs.score_e4}"
        )
    print("  ✓ within-class divergence: primary > variant2 for all 3 classes")

    # 5. Drawdown ranking — momentum variant2 has the heaviest drawdown
    # in the entire scenario (~28% peak-to-trough), so its risk
    # component MUST be lower than primary momentum (no drawdown).
    mom_primary = updates_by_id[ctx.addrs["strategyVaultMomentum"].lower()]
    mom_variant2 = updates_by_id[ctx.addrs["strategyVaultMomentumVariant2"].lower()]
    assert mom_primary.outputs.components.risk > mom_variant2.outputs.components.risk, (
        f"drawdown ranking violated: mom_primary.risk={mom_primary.outputs.components.risk:.3f}"
        f" must exceed mom_variant2.risk={mom_variant2.outputs.components.risk:.3f}"
    )
    # Cross-check: variant2 actually has a meaningful drawdown recorded.
    assert mom_variant2.inputs.max_drawdown_bps_90d > 1000, (
        f"mom_variant2 max_drawdown_bps_90d={mom_variant2.inputs.max_drawdown_bps_90d}"
        " — pump-dump trajectory should produce >10% drawdown"
    )
    print(
        f"  ✓ drawdown ranking: mom_primary.risk={mom_primary.outputs.components.risk:.3f}"
        f" > mom_variant2.risk={mom_variant2.outputs.components.risk:.3f}"
        f" (variant2 dd={mom_variant2.inputs.max_drawdown_bps_90d}bps)"
    )

    print("\nPR3.B: reputation §8.2 GREEN")


def assert_pr3a_oracle_and_nav(ctx: Ctx, start_block: int) -> None:
    """Verify the cadence drivers landed:

    - `Committed` events on both oracle anchors == ANCHOR_COMMITS_PER_ANCHOR
    - `NAVReported` events per vault == NAV_SAMPLES_PER_VAULT
    - Each anchor's commit windows are strictly monotonic (the
      contract enforces this; we cross-check that the read path
      agrees with the write path).
    - NAV trajectories are non-degenerate per vault (final NAV
      differs from initial).
    """
    print("\n=== PR3.A oracle-anchor + NAV-trajectory assertions ===")

    price_logs = _logs(ctx.oracle_price_anchor, "Committed", start_block)
    yield_logs = _logs(ctx.oracle_yield_anchor, "Committed", start_block)
    # `>=` because each trade-emission step appends a per-proof commit
    # for its actual oracle_root after the bulk cadence (PR1a binding —
    # see `_commit_proof_oracle_root`). Adjacency is still verified
    # below across the full sequence.
    assert len(price_logs) >= ANCHOR_COMMITS_PER_ANCHOR, (
        f"expected ≥ {ANCHOR_COMMITS_PER_ANCHOR} OraclePriceAnchor.Committed events, "
        f"got {len(price_logs)}"
    )
    assert len(yield_logs) >= ANCHOR_COMMITS_PER_ANCHOR, (
        f"expected ≥ {ANCHOR_COMMITS_PER_ANCHOR} OracleYieldAnchor.Committed events, "
        f"got {len(yield_logs)}"
    )
    # Window monotonicity — contract refuses overlap, but check that
    # adjacency is exact (windowStart_n == windowEnd_{n-1}).
    for label, logs in (("price", price_logs), ("yield", yield_logs)):
        prev_end = None
        for ev in logs:
            ws = int(ev["args"]["windowStart"])
            we = int(ev["args"]["windowEnd"])
            assert we > ws, f"{label} commit window not strictly positive: {ws}..{we}"
            if prev_end is not None:
                assert ws == prev_end, f"{label} commit cadence broken: ws={ws} prev_we={prev_end}"
            prev_end = we
    print(f"  ✓ OraclePriceAnchor.Committed × {len(price_logs)} (monotonic windows)")
    print(f"  ✓ OracleYieldAnchor.Committed × {len(yield_logs)} (monotonic windows)")

    for (key, _cls), vault in zip(_STRATEGY_VAULT_KEYS, ctx.strategy_vaults, strict=True):
        nav_logs = _logs(vault, "NAVReported", start_block)
        assert len(nav_logs) == NAV_SAMPLES_PER_VAULT, (
            f"{key}: expected {NAV_SAMPLES_PER_VAULT} NAVReported events, got {len(nav_logs)}"
        )
        first = int(nav_logs[0]["args"]["totalNAV"])
        last = int(nav_logs[-1]["args"]["totalNAV"])
        assert first != last, (
            f"{key}: NAV trajectory is flat (start={first}, end={last}); should diverge by class"
        )
    print("  ✓ NAVReported × 30 per vault, 6 distinct trajectories")
    print("\nPR3.A: oracle anchor cadence + NAV trajectories GREEN")


# ── Driver ───────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rpc-url", default=os.environ.get("RPC_URL", "http://127.0.0.1:8545"))
    parser.add_argument(
        "--deployments",
        default=os.environ.get("DEPLOYMENTS_FILE", "contracts/deployments/anvil-kite-phase2.json"),
    )
    parser.add_argument(
        "--prover-url",
        default=os.environ.get("PROVER_URL", "http://127.0.0.1:8004"),
    )
    args = parser.parse_args()

    ctx = _setup(args.rpc_url, Path(args.deployments), args.prover_url)
    print(f"connected: chainId={ctx.chain_id} @ {args.rpc_url}")
    print(f"  deployer={ctx.deployer.address}")
    print(f"  user    ={ctx.user.address}")
    print(f"  prover  ={ctx.prover_url}")
    print(f"  6 strategy vaults loaded from {args.deployments}\n")

    start_block = ctx.w3.eth.block_number

    step_fund(ctx)
    step_set_meta(ctx)
    step_deposit_and_delegate(ctx)
    step_allocate_all(ctx)
    # PR1a (oracle-root binding) requires every proof's `oracle_root` /
    # `yield_oracle_root` PI to be a root the off-chain oracle has
    # actually committed. Drive the bulk anchor cadence FIRST so the
    # 200-bar 90d window is filled, then each trade-emission step
    # appends a fresh single commit for its specific witness root before
    # calling executeWithProof (see `_commit_proof_oracle_root`).
    step_drive_oracle_anchors(ctx)
    step_emit_momentum_trades(ctx)
    step_emit_mean_reversion_trades(ctx)
    step_emit_yield_rotation_trades(ctx)
    step_drive_nav_trajectories(ctx)
    pre_rotation_updates = step_drive_reputation(ctx, start_block)
    step_rotate_params_for_strategy(ctx)
    post_rotation_updates = step_drive_reputation(ctx, start_block)
    bootstrap_result = step_drive_bootstrap_pool(ctx, post_rotation_updates)

    assert_pr1_skeleton(ctx, start_block)
    assert_pr2a_momentum_trades(ctx, start_block)
    assert_pr2b_mean_reversion_trades(ctx, start_block)
    assert_pr2c_yield_rotation_trades(ctx, start_block)
    assert_pr3a_oracle_and_nav(ctx, start_block)
    assert_pr3b_reputation_822(ctx, pre_rotation_updates)
    assert_pr3_5_rotation_reset(ctx, pre_rotation_updates, post_rotation_updates)
    assert_pr3_5c_bootstrap_pool(ctx, bootstrap_result)
    print("\nWS6 PR3.5.C e2e: GREEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
