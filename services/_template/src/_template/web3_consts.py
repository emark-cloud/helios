"""Shared Web3 timing constants for the on-chain anchor posters.

Both `oracle/anchor.py` and `reputation/anchor.py` post EIP-712 commits and
wait for a receipt. They previously declared a `_RECEIPT_TIMEOUT_SEC = 30`
each — moved here so a single bump (e.g. on a slower L2) updates both.

phase2-review.md item 18.
"""

from __future__ import annotations

# Wait this long for an `eth_sendRawTransaction` to be mined before
# raising `TimeExhausted`. 30 s is enough headroom for Kite testnet's
# ~1.5 s blocktime under load, and for Base/Arbitrum testnets which
# can stall briefly during reorgs.
RECEIPT_TIMEOUT_SEC: int = 30
