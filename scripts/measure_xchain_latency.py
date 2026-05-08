"""Phase 5 / WS8 — cross-chain reputation round-trip timing harness.

Demo runbook tool. Listens for `ReputationMessageSent` on a source-chain
HeliosOApp (Base or Arb Sepolia) and pairs each event with the matching
`ReputationMessageReceived` on the Kite HeliosOApp by GUID, then prints
the round-trip latency. Used at demo time to confirm we land inside
the 30-60s budget the plan asserts.

Not a CI gate — running this in CI would couple correctness to live
LayerZero DVN scheduling. The CI gate is the unit-level allocator-
decision test in `services/sentinel/tests/test_phase5_xchain.py`.

Usage:

    KITE_RPC_URL=...  HELIOS_OAPP_KITE=0x...  \
    BASE_SEPOLIA_RPC_URL=...  HELIOS_OAPP_BASE=0x...  \
    python scripts/measure_xchain_latency.py --source base --timeout 120

Exits non-zero if the round-trip exceeds `--max-seconds` (default 60).
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from web3 import Web3
from web3.types import LogReceipt

_OAPP_EVENT_ABI: list[dict] = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "uint32", "name": "dstEid", "type": "uint32"},
            {"indexed": True, "internalType": "address", "name": "actor", "type": "address"},
            {"indexed": False, "internalType": "uint8", "name": "actorType", "type": "uint8"},
            {"indexed": False, "internalType": "bytes32", "name": "guid", "type": "bytes32"},
        ],
        "name": "ReputationMessageSent",
        "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "uint32", "name": "srcEid", "type": "uint32"},
            {"indexed": True, "internalType": "address", "name": "actor", "type": "address"},
            {"indexed": False, "internalType": "uint8", "name": "actorType", "type": "uint8"},
            {"indexed": False, "internalType": "bytes32", "name": "guid", "type": "bytes32"},
        ],
        "name": "ReputationMessageReceived",
        "type": "event",
    },
]


def _env(key: str) -> str:
    v = os.environ.get(key, "").strip()
    if not v:
        print(f"FATAL: env {key} not set", file=sys.stderr)
        sys.exit(2)
    return v


def _hex(b: bytes) -> str:
    return "0x" + b.hex()


def _poll_for_guid(
    *,
    label: str,
    w3: Web3,
    contract,
    event_name: str,
    target_guid: str,
    deadline: float,
) -> tuple[float, LogReceipt] | None:
    """Poll the chain for an event matching `target_guid` until
    `deadline`. Returns the wall-clock time it landed and the log."""
    event = getattr(contract.events, event_name)
    last_block = w3.eth.block_number
    while time.time() < deadline:
        head = w3.eth.block_number
        if head > last_block:
            from_block = last_block + 1
            try:
                logs = event.get_logs(from_block=from_block, to_block=head)
            except Exception as e:
                print(f"[{label}] get_logs error: {e}", file=sys.stderr)
                last_block = head
                time.sleep(2)
                continue
            for log in logs:
                guid_bytes = log["args"]["guid"]
                guid = _hex(guid_bytes) if isinstance(guid_bytes, bytes) else guid_bytes
                if guid.lower() == target_guid.lower():
                    return (time.time(), log)
            last_block = head
        time.sleep(1.5)
    return None


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--source", choices=("base", "arbitrum"), required=True)
    p.add_argument("--timeout", type=int, default=180)
    p.add_argument("--max-seconds", type=int, default=60)
    return p.parse_args()


def _resolve_endpoints(source: str) -> tuple[str, str, str, str]:
    if source == "base":
        return (
            _env("BASE_SEPOLIA_RPC_URL"),
            _env("HELIOS_OAPP_BASE"),
            _env("KITE_RPC_URL"),
            _env("HELIOS_OAPP_KITE"),
        )
    return (
        _env("ARBITRUM_SEPOLIA_RPC_URL"),
        _env("HELIOS_OAPP_ARB"),
        _env("KITE_RPC_URL"),
        _env("HELIOS_OAPP_KITE"),
    )


def _wait_for_sent(w3: Web3, contract, deadline: float) -> tuple[float, str] | None:
    src_event = contract.events.ReputationMessageSent
    last_block = w3.eth.block_number
    while time.time() < deadline:
        head = w3.eth.block_number
        if head > last_block:
            try:
                logs = src_event.get_logs(from_block=last_block + 1, to_block=head)
            except Exception as e:
                print(f"[src] get_logs error: {e}", file=sys.stderr)
                last_block = head
                time.sleep(2)
                continue
            for log in logs:
                gb = log["args"]["guid"]
                guid = _hex(gb) if isinstance(gb, bytes) else gb
                print(f"[src] ReputationMessageSent guid={guid} block={log['blockNumber']}")
                return (time.time(), guid)
            last_block = head
        time.sleep(1.5)
    return None


def main() -> int:
    args = _parse_args()
    src_rpc, src_oapp, dst_rpc, dst_oapp = _resolve_endpoints(args.source)

    src_w3 = Web3(Web3.HTTPProvider(src_rpc))
    dst_w3 = Web3(Web3.HTTPProvider(dst_rpc))
    src_contract = src_w3.eth.contract(
        address=Web3.to_checksum_address(src_oapp),
        abi=_OAPP_EVENT_ABI,
    )
    dst_contract = dst_w3.eth.contract(
        address=Web3.to_checksum_address(dst_oapp),
        abi=_OAPP_EVENT_ABI,
    )

    deadline = time.time() + args.timeout
    print(
        f"[harness] listening on {args.source} for ReputationMessageSent (timeout={args.timeout}s)",
    )

    sent = _wait_for_sent(src_w3, src_contract, deadline)
    if sent is None:
        print(
            "[harness] FAIL: no ReputationMessageSent observed before timeout",
            file=sys.stderr,
        )
        return 1
    sent_at, sent_guid = sent

    print(f"[dst] waiting for ReputationMessageReceived guid={sent_guid} on Kite")
    pair = _poll_for_guid(
        label="dst",
        w3=dst_w3,
        contract=dst_contract,
        event_name="ReputationMessageReceived",
        target_guid=sent_guid,
        deadline=deadline,
    )
    if pair is None:
        print(
            "[harness] FAIL: ReputationMessageReceived not observed on Kite before timeout",
            file=sys.stderr,
        )
        return 1

    received_at, log = pair
    elapsed = received_at - sent_at
    print(f"[harness] round-trip: {elapsed:.1f}s (block={log['blockNumber']})")
    if elapsed > args.max_seconds:
        print(
            f"[harness] FAIL: round-trip {elapsed:.1f}s exceeds budget {args.max_seconds}s",
            file=sys.stderr,
        )
        return 1
    print(f"[harness] PASS: round-trip inside {args.max_seconds}s budget")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
