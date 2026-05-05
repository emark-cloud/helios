"""One-shot verification: post a sample commit to OraclePriceAnchor +
OracleYieldAnchor on Kite testnet, then poll the v0.2.0 subgraph until
both `OraclePriceCommit` and `OracleYieldCommit` rows show up.

This validates the full Phase-2 plumbing end-to-end:
  - EIP-712 signing path in `oracle.anchor.sign_commit`
  - On-chain `commit()` accepts the signature (deployer-as-signer)
  - Goldsky datasource picks up `Committed` event
  - Mapping writes the right fields into the schema entity

Reads contract addresses + deployer PK + RPC + Goldsky endpoint from the
ambient environment (`source .env` first). Bypasses the long-lived oracle
service so we don't need to feed it real Binance snapshots.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import httpx
from web3 import Web3

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "services" / "oracle" / "src"))

from oracle.anchor import CommitPayload, sign_commit  # noqa: E402

CHAIN_ID = 2368


_COMMIT_ABI = [
    {
        "type": "function",
        "name": "commit",
        "inputs": [
            {"name": "root", "type": "bytes32"},
            {"name": "windowStart", "type": "uint64"},
            {"name": "windowEnd", "type": "uint64"},
            {"name": "sig", "type": "bytes"},
        ],
        "outputs": [],
        "stateMutability": "nonpayable",
    },
    {
        "type": "function",
        "name": "nonce",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
    },
]


def _commit(
    w3: Web3,
    deployer_pk: str,
    anchor_addr: str,
    kind: str,
    *,
    window_start: int,
    window_end: int,
    seed: int,
) -> str:
    contract = w3.eth.contract(address=Web3.to_checksum_address(anchor_addr), abi=_COMMIT_ABI)
    on_chain_nonce = int(contract.functions.nonce().call())

    # Random-ish 32-byte root keyed off `kind + seed` so re-runs don't collide.
    root = (seed % (2**256 - 1)).to_bytes(32, "big")

    payload = CommitPayload(
        kind=kind,  # type: ignore[arg-type]
        root=root,
        window_start=window_start,
        window_end=window_end,
        nonce=on_chain_nonce,
    )
    signed = sign_commit(payload, deployer_pk, CHAIN_ID, anchor_addr)

    sender = signed.signer
    fn = contract.functions.commit(root, window_start, window_end, signed.signature)
    tx = fn.build_transaction(
        {
            "from": Web3.to_checksum_address(sender),
            "nonce": w3.eth.get_transaction_count(Web3.to_checksum_address(sender), "pending"),
            "chainId": CHAIN_ID,
            "gasPrice": w3.eth.gas_price,
        }
    )
    signed_tx = w3.eth.account.sign_transaction(tx, deployer_pk)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
    if receipt["status"] != 1:
        raise RuntimeError(f"{kind} commit reverted: {tx_hash.hex()}")
    print(f"  {kind} committed @ block {receipt['blockNumber']}, tx {tx_hash.hex()}")
    return root.hex()


def _poll(endpoint: str, entity: str, root_hex: str, timeout_sec: int = 90) -> dict | None:
    query = (
        '{ %s(where: { root: "0x%s" }) { id index root windowStart windowEnd signer committedAt } }'
        % (entity, root_hex)
    )
    deadline = time.time() + timeout_sec
    last = None
    while time.time() < deadline:
        r = httpx.post(endpoint, json={"query": query}, timeout=10.0)
        rows = r.json().get("data", {}).get(entity, [])
        if rows:
            return rows[0]
        last = r.json()
        time.sleep(3)
    print(f"  TIMEOUT — last response: {last}")
    return None


def main() -> int:
    rpc = os.environ["KITE_RPC_URL"]
    deployer_pk = os.environ["DEPLOYER_PK"]
    price_addr = os.environ["ORACLE_PRICE_ANCHOR_ADDRESS"]
    yield_addr = os.environ["ORACLE_YIELD_ANCHOR_ADDRESS"]
    endpoint = os.environ["GOLDSKY_ENDPOINT"]

    w3 = Web3(Web3.HTTPProvider(rpc))
    now_ms = int(time.time() * 1000)

    print("→ Posting OraclePriceAnchor commit")
    price_root = _commit(
        w3,
        deployer_pk,
        price_addr,
        "price",
        window_start=now_ms - 60_000,
        window_end=now_ms - 30_000,
        seed=now_ms,
    )

    print("→ Posting OracleYieldAnchor commit")
    yield_root = _commit(
        w3,
        deployer_pk,
        yield_addr,
        "yield",
        window_start=now_ms - 60_000,
        window_end=now_ms - 30_000,
        seed=now_ms + 1,
    )

    print("→ Polling subgraph for OraclePriceCommit")
    p = _poll(endpoint, "oraclePriceCommits", price_root)
    print(f"  {p}")

    print("→ Polling subgraph for OracleYieldCommit")
    y = _poll(endpoint, "oracleYieldCommits", yield_root)
    print(f"  {y}")

    return 0 if p and y else 1


if __name__ == "__main__":
    sys.exit(main())
