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
    MOMENTUM_V1 as CLASS_MOM_BYTES32,
    YIELD_ROTATION_V1 as CLASS_YR_BYTES32,
)
from helios_contracts_abi.abis import (
    IAllocatorVault_ABI,
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
from _phase2_witness import build_momentum_witness  # noqa: E402

# Reuse the helios-cli encoder for proof bytes — single source of truth
# for the snarkjs Fp2 imag/real swap. Available via uv workspace.
from helios_cli._proof import (  # noqa: E402
    proof_to_bytes,
    public_signals_to_uints,
)

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
    usdc: Contract
    prover_url: str


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
        usdc=usdc,
        prover_url=prover_url,
    )


# ── Steps ────────────────────────────────────────────────────


def step_fund(ctx: Ctx) -> None:
    print(f"[1] fund user with {_DEPOSIT_USDC // 1000}k mUSDC")
    _send(
        ctx.w3, ctx.deployer, ctx.usdc.functions.mint(ctx.user.address, _DEPOSIT_USDC * 10**6)
    )
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
    print(
        f"[3] user approve + deposit {_DEPOSIT_USDC // 1000}k mUSDC + delegate to AllocatorVault"
    )
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


def _prove(prover_url: str, witness_inputs: dict[str, Any]) -> dict[str, Any]:
    """Synchronous httpx call to the local prover service. snarkjs proof gen
    on the momentum_v1 circuit clocks ~2-5s on dev hardware; allow 60s."""
    resp = httpx.post(
        f"{prover_url.rstrip('/')}/prove",
        json={"strategyClass": "momentum_v1", "witnessInputs": witness_inputs},
        timeout=60.0,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"prover {resp.status_code}: {resp.text}")
    return resp.json()


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
        ("strategyVaultMomentum",         ctx.strategy_vaults[0], _kite_long_series_a()),
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
        # 3. Generate proof.
        print("    proving (snarkjs.fullProve)…")
        result = _prove(ctx.prover_url, witness.inputs)
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
    our_allocs = [
        e for e in alloc_created
        if e["args"]["user"].lower() == user_addr
    ]
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


# ── Driver ───────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rpc-url", default=os.environ.get("RPC_URL", "http://127.0.0.1:8545"))
    parser.add_argument(
        "--deployments",
        default=os.environ.get(
            "DEPLOYMENTS_FILE", "contracts/deployments/anvil-kite-phase2.json"
        ),
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
    step_emit_momentum_trades(ctx)

    assert_pr1_skeleton(ctx, start_block)
    assert_pr2a_momentum_trades(ctx, start_block)
    print("\nWS6 PR2.A e2e: GREEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
