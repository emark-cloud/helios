"""WS3 — Phase 1 e2e scenario orchestrator.

Drives the full vertical slice against a deployed Phase 1 stack:

  user signs meta-strategy (EOA stub for Passport)
  → deposit + delegate
  → operator allocates
  → strategy emits TradeAttested via executeWithProof
  → reputation engine posts a signed score update on-chain
  → NAV drops past the user's drawdown threshold
  → a *non-allocator* EOA calls defundStrategy (permissionless path)
  → operator allocates a replacement strategy
  → assert every event landed via eth_getLogs

Track A: invoked by `scripts/e2e-scenario.sh` against the docker-compose
anvil-kite (or a standalone anvil started by the wrapper). Mock Groth16
verifier (per `DeployPhase1.s.sol`) — proof bytes are arbitrary; the
TradeAttested path still exercises the full StrategyVault validation
(public-input length, asset-universe bounds, block window, trade hash
uniqueness). Real Groth16 round-trip is independently certified by
`MomentumV1Verifier.t.sol`.

Track B: same script, `RPC_URL=$KITE_RPC_URL` and `DEPLOYER_PK=...`
in env. Broadcasts to Kite testnet, gives judges live tx hashes.

Hard gate (`Helios.md §6.3`): the permissionless-defund tx is sent
from `_STRANGER_PK` (a separate funded EOA, not the operator). The
script asserts the StrategyDefunded log carries that caller in its
indexed `caller` topic.
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

from eth_abi.abi import encode as abi_encode
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_keys.datatypes import PrivateKey
from eth_utils.crypto import keccak
from helios_contracts_abi.abis import (
    IAllocatorVault_ABI,
    IReputationAnchor_ABI,
    IStrategyVault_ABI,
    IUserVault_ABI,
)
from web3 import Web3
from web3.contract.contract import Contract

# ── Anvil default keys (deterministic mnemonic).
# Operator = anvil[0] = deployer per DeployPhase1.s.sol.
# User     = anvil[1] (the [PASSPORT-STUB]).
# Stranger = anvil[2] (the permissionless defund caller; never operator).
_OPERATOR_PK = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
_USER_PK = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
_STRANGER_PK = "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a"

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


@dataclass
class Ctx:
    w3: Web3
    chain_id: int
    addrs: dict[str, str]
    deployer: Any
    user: Any
    stranger: Any
    user_vault: Contract
    allocator_vault: Contract
    strategy_momentum: Contract
    strategy_meanrev: Contract
    reputation_anchor: Contract
    usdc: Contract


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


def _setup(rpc_url: str, deployments: Path) -> Ctx:
    w3 = _wait_for_rpc(rpc_url)
    chain_id = w3.eth.chain_id
    addrs = _load_addresses(deployments)
    deployer = Account.from_key(_OPERATOR_PK)
    user = Account.from_key(_USER_PK)
    stranger = Account.from_key(_STRANGER_PK)

    user_vault = w3.eth.contract(
        address=Web3.to_checksum_address(addrs["userVault"]), abi=IUserVault_ABI
    )
    allocator_vault = w3.eth.contract(
        address=Web3.to_checksum_address(addrs["allocatorVault"]), abi=IAllocatorVault_ABI
    )
    strategy_momentum = w3.eth.contract(
        address=Web3.to_checksum_address(addrs["strategyVaultMomentum"]),
        abi=IStrategyVault_ABI,
    )
    strategy_meanrev = w3.eth.contract(
        address=Web3.to_checksum_address(addrs["strategyVaultMeanReversion"]),
        abi=IStrategyVault_ABI,
    )
    reputation_anchor = w3.eth.contract(
        address=Web3.to_checksum_address(addrs["reputationAnchor"]),
        abi=IReputationAnchor_ABI,
    )
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
        stranger=stranger,
        user_vault=user_vault,
        allocator_vault=allocator_vault,
        strategy_momentum=strategy_momentum,
        strategy_meanrev=strategy_meanrev,
        reputation_anchor=reputation_anchor,
        usdc=usdc,
    )


# ── Steps ────────────────────────────────────────────────────


def step_fund(ctx: Ctx) -> None:
    """Mint mUSDC to user, send KITE gas to user + stranger (anvil pre-funds
    these but on Kite testnet a fresh demo wallet wouldn't be)."""
    print("[1] fund user with 100k mUSDC + gas")
    _send(ctx.w3, ctx.deployer, ctx.usdc.functions.mint(ctx.user.address, 100_000 * 10**6))
    bal = ctx.usdc.functions.balanceOf(ctx.user.address).call()
    assert bal == 100_000 * 10**6, f"user mUSDC balance {bal} unexpected"


def step_set_meta(ctx: Ctx) -> bytes:
    """User signs + posts the meta-strategy. [PASSPORT-STUB]: signature is
    carried in storage for forward compat but not verified — the user IS
    the caller. We build a structurally-valid EIP-712 sig anyway so the
    audit trail looks right when Passport swaps in."""
    print("[2] user setMetaStrategy")
    momentum_class = keccak(b"momentum_v1")
    meanrev_class = keccak(b"mean_reversion_v1")
    meta_struct = (
        keccak(b"phase1-demo-meta"),  # metaStrategyHash (Poseidon in real Passport)
        [momentum_class, meanrev_class],  # allowedStrategyClasses
        [Web3.to_checksum_address(ctx.addrs["usdc"])],  # allowedAssets
        [ctx.chain_id],  # allowedChains
        100_000 * 10**6,  # maxCapital (100k USDC)
        10_000,  # maxPerStrategyBps (100% — no per-strat cap)
        2,  # maxStrategiesCount
        1_500,  # drawdownThresholdBps (15%)
        2_500,  # maxFeeRateBps
        3_600,  # rebalanceCadenceSec (1h)
        0,  # validUntil (never expires)
    )
    # [PASSPORT-STUB] EIP-712 sig — UserVault.setMetaStrategy doesn't verify
    # in Phase 1, but we sign over a structurally-valid payload so the
    # checked-in artifact mirrors what Passport will produce.
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
    print("[3] user approve + deposit 50k mUSDC + delegate to AllocatorVault")
    _send(
        ctx.w3,
        ctx.user,
        ctx.usdc.functions.approve(ctx.user_vault.address, 50_000 * 10**6),
    )
    _send(
        ctx.w3,
        ctx.user,
        ctx.user_vault.functions.deposit(
            Web3.to_checksum_address(ctx.addrs["usdc"]), 50_000 * 10**6
        ),
    )
    _send(
        ctx.w3,
        ctx.user,
        ctx.user_vault.functions.delegateToAllocator(ctx.allocator_vault.address, 86_400),
    )


def step_allocate(ctx: Ctx, strategy: str, amount_usdc: int) -> dict[str, Any]:
    print(f"[4] operator allocateToStrategy({strategy[:10]}…, {amount_usdc} USDC)")
    return _send(
        ctx.w3,
        ctx.deployer,
        ctx.allocator_vault.functions.allocateToStrategy(
            ctx.user.address, Web3.to_checksum_address(strategy), amount_usdc * 10**6
        ),
    )


def step_execute_with_proof(ctx: Ctx, strategy: Contract) -> dict[str, Any]:
    """Send executeWithProof with mock-friendly publicInputs.

    DeployPhase1 registers MockGroth16Verifier(true) for momentum_v1 in
    Track A — proof bytes can be empty. trades=[] skips the swap (which
    would need real router calldata); the StrategyVault still emits
    TradeAttested with the full public-input payload, and that's what
    the subgraph + reputation engine consume.
    """
    print("[5] operator executeWithProof (mock verifier; trades=[] skips swap)")
    block = ctx.w3.eth.block_number
    public_inputs = [
        0,  # asset_in (universe[0] = USDC)
        0,  # asset_out
        1_000 * 10**6,  # amount_in (1k USDC notional)
        990 * 10**6,  # min_amount_out
        1,  # direction (long)
        block,  # window_start
        block + 50,  # window_end
        int.from_bytes(keccak(b"phase1-e2e-trade-1")[:32], "big"),  # trade_hash
    ]
    return _send(
        ctx.w3,
        ctx.deployer,
        # TradeAttestationVerifier requires exactly 256 bytes
        # (abi.encode(uint256[2], uint256[2][2], uint256[2])).
        strategy.functions.executeWithProof(b"\x00" * 256, public_inputs, []),
    )


def step_report_nav(ctx: Ctx, strategy: Contract, total_nav: int, ts: int) -> dict[str, Any]:
    """`total_nav` is in the strategy's base-asset units (USDC = 6 decimals).
    Matched against capitalDeployed / strategyHighWaterMark in the same
    base-asset units inside `AllocatorVault.defundStrategy`."""
    print(f"[6] navOracle reportNAV({total_nav / 10**6:.2f} USDC @ ts={ts})")
    # Match StrategyVault.reportNAV exactly:
    #   digest = keccak256(abi.encode(address(this), totalNAV_, timestamp))
    # where timestamp is uint64 — both width-padded to 32 bytes by abi.encode.
    body = abi_encode(
        ["address", "uint256", "uint64"],
        [strategy.address, total_nav, ts],
    )
    digest = keccak(body)
    pk_obj = PrivateKey(bytes.fromhex(_OPERATOR_PK[2:]))
    sig_obj = pk_obj.sign_msg_hash(digest)
    # OZ v5 ECDSA.tryRecover expects v ∈ {27,28} for 65-byte sigs;
    # eth_keys returns v ∈ {0,1} — bump to 27/28.
    sig_raw = sig_obj.to_bytes()
    sig = sig_raw[:64] + bytes([sig_raw[64] + 27])
    signed_nav = abi_encode(["uint256", "uint64", "bytes"], [total_nav, ts, sig])
    return _send(ctx.w3, ctx.deployer, strategy.functions.reportNAV(signed_nav))


def step_permissionless_defund(ctx: Ctx, strategy_addr: str) -> dict[str, Any]:
    print("[7] STRANGER (non-operator) defundStrategy — permissionless path")
    receipt = _send(
        ctx.w3,
        ctx.stranger,
        ctx.allocator_vault.functions.defundStrategy(
            ctx.user.address,
            Web3.to_checksum_address(strategy_addr),
            "phase1-e2e-permissionless",
        ),
    )
    return receipt


def step_replacement_allocate(ctx: Ctx) -> dict[str, Any]:
    """After defund, operator allocates capital into mean_reversion strategy
    as the replacement. Phase 1 Sentinel does this on its rebalance tick;
    here we drive it directly to keep the e2e single-process."""
    return step_allocate(ctx, ctx.addrs["strategyVaultMeanReversion"], 5_000)


def step_post_reputation(ctx: Ctx) -> dict[str, Any]:
    """Reputation engine path: sign a score update + post via the anchor.
    Uses the deployer key as both signer and submitter, matching how the
    reputation service is configured for Track A."""
    print("[8] reputation engine post score for momentum strategy")
    actor = Web3.to_checksum_address(ctx.addrs["strategyVaultMomentum"])
    actor_type = 0  # ActorType.STRATEGY
    score = 7_500  # +75% of full credit
    block = ctx.w3.eth.block_number
    domain = {
        "name": "HeliosReputationAnchor",
        "version": "1",
        "chainId": ctx.chain_id,
        "verifyingContract": Web3.to_checksum_address(ctx.addrs["reputationAnchor"]),
    }
    types = {
        "ReputationUpdate": [
            {"name": "actor", "type": "address"},
            {"name": "actorType", "type": "uint8"},
            {"name": "currentScore", "type": "int256"},
            {"name": "lastUpdateBlock", "type": "uint256"},
            {"name": "totalAttestedTrades", "type": "uint256"},
            {"name": "totalRealizedPnL", "type": "uint256"},
            {"name": "maxDrawdownBps", "type": "uint256"},
            {"name": "proofValidityRateBps", "type": "uint256"},
        ]
    }
    message = {
        "actor": actor,
        "actorType": actor_type,
        "currentScore": score,
        "lastUpdateBlock": block,
        "totalAttestedTrades": 1,
        "totalRealizedPnL": 0,
        "maxDrawdownBps": 0,
        "proofValidityRateBps": 10_000,
    }
    encoded = encode_typed_data(domain_data=domain, message_types=types, message_data=message)
    sig = ctx.deployer.sign_message(encoded).signature
    data_tuple = (score, block, 1, 0, 0, 10_000, actor_type)
    return _send(
        ctx.w3,
        ctx.deployer,
        ctx.reputation_anchor.functions.postReputationUpdate(actor, actor_type, data_tuple, sig),
    )


# ── Assertions ───────────────────────────────────────────────


def _logs(ctx: Ctx, contract: Contract, event_name: str, from_block: int) -> list[Any]:
    event = getattr(contract.events, event_name)
    return list(event.get_logs(from_block=from_block, to_block="latest"))


def assert_events(ctx: Ctx, start_block: int) -> None:
    print("\n=== Asserting on-chain log trail ===")
    alloc_created = _logs(ctx, ctx.allocator_vault, "AllocationCreated", start_block)
    trade_attested = _logs(ctx, ctx.strategy_momentum, "TradeAttested", start_block)
    nav_reports = _logs(ctx, ctx.strategy_momentum, "NAVReported", start_block)
    defund = _logs(ctx, ctx.allocator_vault, "StrategyDefunded", start_block)
    rep_posted = _logs(ctx, ctx.reputation_anchor, "ReputationPosted", start_block)

    assert len(alloc_created) >= 2, f"expected ≥2 AllocationCreated, got {len(alloc_created)}"
    assert len(trade_attested) >= 1, f"expected ≥1 TradeAttested, got {len(trade_attested)}"
    assert len(nav_reports) >= 2, f"expected ≥2 NAVReported, got {len(nav_reports)}"
    assert len(defund) == 1, f"expected exactly 1 StrategyDefunded, got {len(defund)}"
    assert len(rep_posted) >= 1, f"expected ≥1 ReputationPosted, got {len(rep_posted)}"

    # Hard gate per Helios.md §6.3 — defund caller must NOT be the allocator's operator.
    defund_event = defund[0]
    caller = defund_event["args"]["triggeredBy"]
    stranger = ctx.stranger.address
    assert caller.lower() == stranger.lower(), (
        f"permissionless-defund hard gate FAILED: triggeredBy {caller} != stranger {stranger}"
    )
    print(f"  ✓ AllocationCreated x{len(alloc_created)}")
    print(f"  ✓ TradeAttested    x{len(trade_attested)}")
    print(f"  ✓ NAVReported      x{len(nav_reports)}")
    print(f"  ✓ StrategyDefunded x{len(defund)} (caller={caller[:10]}…, stranger ✓)")
    print(f"  ✓ ReputationPosted x{len(rep_posted)}")
    print("\nPermissionless-defund hard gate (Helios.md §6.3): PASSED")


# ── Driver ───────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rpc-url", default=os.environ.get("RPC_URL", "http://127.0.0.1:8545"))
    parser.add_argument(
        "--deployments",
        default=os.environ.get("DEPLOYMENTS_FILE", "contracts/deployments/anvil-kite.json"),
    )
    args = parser.parse_args()

    ctx = _setup(args.rpc_url, Path(args.deployments))
    print(f"connected: chainId={ctx.chain_id} @ {args.rpc_url}")
    print(f"  deployer={ctx.deployer.address}")
    print(f"  user    ={ctx.user.address}")
    print(f"  stranger={ctx.stranger.address}\n")

    start_block = ctx.w3.eth.block_number

    step_fund(ctx)
    step_set_meta(ctx)
    step_deposit_and_delegate(ctx)
    step_allocate(ctx, ctx.addrs["strategyVaultMomentum"], 10_000)
    step_execute_with_proof(ctx, ctx.strategy_momentum)
    step_post_reputation(ctx)

    # NAV is reported in the same base units as the underlying asset
    # (USDC = 6 decimals here). Allocation = 10_000e6, HWM = 10_000e6;
    # drop NAV to 8_000e6 → 20% drawdown > 15% meta threshold → permissionless
    # defund unlocks.
    base_ts = int(time.time())
    step_report_nav(ctx, ctx.strategy_momentum, 10_000 * 10**6, base_ts)
    step_report_nav(ctx, ctx.strategy_momentum, 8_000 * 10**6, base_ts + 1)

    step_permissionless_defund(ctx, ctx.addrs["strategyVaultMomentum"])
    step_replacement_allocate(ctx)

    assert_events(ctx, start_block)
    print("\nWS3 e2e: GREEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
