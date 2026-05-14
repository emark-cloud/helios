"""AllocatorOnChain — the SDK's chain client.

Three responsibilities:

1. Read live state from the AllocatorVault + StrategyVault that Goldsky
   doesn't yet surface fast enough — `AllocatorVault.allocationOf(user,
   strategy)` (capital deployed + HWM + defundedAt) and
   `StrategyVault.navOf(allocatorVault)` (current NAV share).
2. Submit the four operator-driven calls: `allocateToStrategy`,
   `defundStrategy`, `rebalance`, `settleStrategyFee`.
3. Register the allocator on `AllocatorRegistry` with its supported
   classes / fee rate / stake amount. Callable once at boot via
   `register_allocator(...)` — third-party allocators built from
   `helios-allocator init` invoke this from a one-shot CLI step.

Address-gated: when `allocator_vault_address` is unset, the runner is a
no-op that records what it *would have* done. Same posture as the
reputation engine's `REPUTATION_ANCHOR_ADDRESS` gate. Sentinel and
Helix both rely on this for scenario / dry-run / unit-test paths.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import structlog
from eth_account import Account
from helios_contracts_abi.abis import IAllocatorRegistry_ABI, IAllocatorVault_ABI
from web3 import Web3
from web3.types import TxReceipt

from helios_allocator.runtime.state import AllocationState

# 30s mirrors `services/_template/src/_template/web3_consts.RECEIPT_TIMEOUT_SEC`.
# Inlined here to keep the SDK free of workspace-only runtime dependencies
# (the SDK ships to PyPI; `_template` does not). See
# `project_strategy_sdk_distribution.md` memory.
RECEIPT_TIMEOUT_SEC: int = 30

# Minimal balanceOf fragment for UserVault. The generated `IUserVault_ABI`
# in `helios-contracts-abi-py` only ships the operator-facing surface
# (deposit/setMetaStrategy/delegateToAllocator/withdraw + events), not
# the per-user balance accessor. Inlining here avoids a binding-regen
# cycle for a single read-only call. Signature matches
# `UserVault.balanceOf(address)` in `contracts/src/UserVault.sol:279`.
_USER_VAULT_BALANCE_ABI: tuple[dict[str, Any], ...] = (
    {
        "type": "function",
        "name": "balanceOf",
        "stateMutability": "view",
        "inputs": [{"name": "user", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
)

# `lastNAVTimestamp` is the unix-seconds timestamp of the most recent
# NAV update accepted by `StrategyVault.reportNAV`. We read it directly
# so the allocator can gate on "is the navOracle actively posting"
# without depending on subgraph NAVSnapshot indexing — the subgraph
# can be slow to backfill new vault deployments, and an authoritative
# RPC read is the right source of truth anyway.
_STRATEGY_VAULT_LAST_NAV_ABI: tuple[dict[str, Any], ...] = (
    {
        "type": "function",
        "name": "lastNAVTimestamp",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint64"}],
    },
)

# CXR-0c — Minimal OFT.quoteSend fragment so the allocator can price an
# `allocateToRemoteStrategy` call before submitting. The result feeds the
# `MessagingFee` calldata arg + the tx `value` field.
_OFT_QUOTE_SEND_ABI: tuple[dict[str, Any], ...] = (
    {
        "type": "function",
        "name": "quoteSend",
        "stateMutability": "view",
        "inputs": [
            {
                "name": "_sendParam",
                "type": "tuple",
                "components": [
                    {"name": "dstEid", "type": "uint32"},
                    {"name": "to", "type": "bytes32"},
                    {"name": "amountLD", "type": "uint256"},
                    {"name": "minAmountLD", "type": "uint256"},
                    {"name": "extraOptions", "type": "bytes"},
                    {"name": "composeMsg", "type": "bytes"},
                    {"name": "oftCmd", "type": "bytes"},
                ],
            },
            {"name": "_payInLzToken", "type": "bool"},
        ],
        "outputs": [
            {
                "name": "msgFee",
                "type": "tuple",
                "components": [
                    {"name": "nativeFee", "type": "uint256"},
                    {"name": "lzTokenFee", "type": "uint256"},
                ],
            },
        ],
    },
)

# Solidity-side: `CXR_ACTION_ALLOCATE = 0`. Mirror here so we encode the
# compose payload the way HeliosBridgeReceiver.sol expects.
_CXR_ACTION_ALLOCATE: int = 0
# Tier 2 — batched ALLOCATE. ComposeMsg encodes arrays + a single user.
# Receiver loops `_allocateOne` per index. Amortizes the LZ V2 fixed
# fee across N strategies on the same destination chain. Mirror of
# `AllocatorVault.CXR_ACTION_ALLOCATE_BATCH` / `HeliosBridgeReceiver.ACTION_ALLOCATE_BATCH`.
_CXR_ACTION_ALLOCATE_BATCH: int = 2

# LayerZero V2 Type-3 options TLV — defaults to:
#   - lzReceive: 200_000 gas (OFT release on the destination chain)
#   - lzCompose @ index 0: 500_000 gas (BridgeReceiver dispatch +
#     StrategyVault.onCrossChainAllocate accounting write)
# Encoded by hand from the OptionsBuilder.sol layout in @layerzerolabs:
#   prefix 0x0003
#   worker 0x01 | size 0x0011 | type 0x01 | gas (uint128 BE)
#   worker 0x01 | size 0x0013 | type 0x03 | index (uint16 BE) | gas (uint128 BE)
_DEFAULT_LZ_EXTRA_OPTIONS: bytes = bytes.fromhex(
    "0003"
    "010011" "01" "00000000000000000000000000030d40"  # lzReceive 200_000
    "010013" "03" "0000" "00000000000000000000000000030d40"  # lzCompose 200_000
)
# The compose handler (`HeliosBridgeReceiver._allocate`) does a single
# ERC20.safeTransfer + try-call into the StrategyVault's
# onCrossChainAllocate (state write + event emit) + catch-fallthrough
# to recoverable[]. Measured envelope: ~120-180k gas (cold storage
# user-mapping slot dominates). 200_000 covers that with margin; the
# old 500_000 was a CXR-0c scaffold default that overpaid the Kite
# testnet executor fee ~2× (~1.2 KITE/call → ~0.5 KITE).

# CXR-0c — local fragment for `allocateToRemoteStrategy`. The shared
# `IAllocatorVault_ABI` only ships interface methods; the cross-chain
# entry point lives on the concrete contract. Inline here so the runner
# doesn't depend on a fresh ABI regen + workspace install round-trip.
_ALLOCATE_TO_REMOTE_ABI: tuple[dict[str, Any], ...] = (
    {
        "type": "function",
        "name": "allocateToRemoteStrategy",
        "stateMutability": "payable",
        "inputs": [
            {"name": "user", "type": "address"},
            {"name": "strategyId", "type": "bytes32"},
            {"name": "amount", "type": "uint256"},
            {"name": "dstEid", "type": "uint32"},
            {"name": "remoteVault", "type": "address"},
            {"name": "extraOptions", "type": "bytes"},
            {
                "name": "lzFee",
                "type": "tuple",
                "components": [
                    {"name": "nativeFee", "type": "uint256"},
                    {"name": "lzTokenFee", "type": "uint256"},
                ],
            },
        ],
        "outputs": [],
    },
    # Tier 2 — batched variant. Single struct arg `RemoteBatchParams` to
    # stay under via-IR stack-depth on the solidity side; web3 encodes
    # the tuple from the ordered Python value.
    {
        "type": "function",
        "name": "allocateToRemoteStrategyBatch",
        "stateMutability": "payable",
        "inputs": [
            {
                "name": "p",
                "type": "tuple",
                "components": [
                    {"name": "user", "type": "address"},
                    {"name": "strategyIds", "type": "bytes32[]"},
                    {"name": "amounts", "type": "uint256[]"},
                    {"name": "remoteVaults", "type": "address[]"},
                    {"name": "dstEid", "type": "uint32"},
                    {"name": "extraOptions", "type": "bytes"},
                    {
                        "name": "lzFee",
                        "type": "tuple",
                        "components": [
                            {"name": "nativeFee", "type": "uint256"},
                            {"name": "lzTokenFee", "type": "uint256"},
                        ],
                    },
                ],
            },
        ],
        "outputs": [],
    },
)

_log = structlog.get_logger(__name__)


@dataclass(slots=True)
class OnChainCall:
    """A planned (and possibly submitted) chain call.

    Mutable so the live path can attach tx_hash / receipt status without
    forcing the dry-run path to allocate a separate result type.
    """

    method: str
    user: str
    strategy: str | None
    amount: int = 0
    reason: str = ""
    weights_bps: tuple[int, ...] = ()
    strategies: tuple[str, ...] = ()
    tx_hash: str = ""
    submitted: bool = False
    error: str = ""
    # CXR-0c — extra fields used only by `allocateToRemoteStrategy`.
    dst_eid: int = 0
    remote_vault: str = ""
    extra_options: bytes = b""
    lz_native_fee: int = 0
    lz_token_fee: int = 0
    strategy_id_bytes32: bytes = b""
    # Tier 2 — batched-allocate fields. Populated by
    # `allocate_to_remote_batch`; empty for all other methods.
    batch_strategy_ids: tuple[str, ...] = ()
    batch_strategy_ids_bytes32: tuple[bytes, ...] = ()
    batch_amounts: tuple[int, ...] = ()
    batch_remote_vaults: tuple[str, ...] = ()


class AllocatorOnChain:
    """Tx-submission boundary.

    Live mode: takes a `web3.Web3` + signing key, submits real txs.
    Stub mode: when `allocator_vault_address` is empty, records calls
    in `pending` for tests / dry-runs. The decision loop never branches
    on which mode is active — it just calls into the runner.
    """

    def __init__(
        self,
        rpc_url: str,
        operator_pk: str,
        allocator_vault_address: str,
        allocator_registry_address: str,
        chain_id: int,
        user_vault_address: str = "",
        oft_adapter_address: str = "",
        remote_chain_eids: dict[int, int] | None = None,
        remote_vault_overrides: dict[str, str] | None = None,
    ) -> None:
        self._rpc_url = rpc_url
        self._operator_pk = operator_pk
        self._allocator_vault = allocator_vault_address
        self._allocator_registry = allocator_registry_address
        self._user_vault = user_vault_address
        self._chain_id = chain_id
        self._live = bool(rpc_url and operator_pk and allocator_vault_address)
        self.pending: list[OnChainCall] = []

        # CXR-0c — remote allocation wiring. Allocator can flip to a live
        # `allocateToRemoteStrategy` send only when ALL three are set:
        # OFT adapter address, an entry in the `remote_chain_eids` map for
        # the destination chain, and a `remote_vault_overrides` entry for
        # the strategy id (or the strategy id itself is already the vault
        # address). Otherwise the loop falls back to defer-mode.
        self._oft_adapter = oft_adapter_address
        self._remote_chain_eids = dict(remote_chain_eids or {})
        self._remote_vault_overrides = {
            k.lower(): v for k, v in (remote_vault_overrides or {}).items()
        }

        # Live-mode handles initialised lazily on first submit so dry-run
        # tests don't need to spin up an RPC client.
        self._w3: Web3 | None = None
        self._account: Any = None
        self._vault_contract: Any = None
        self._registry_contract: Any = None
        self._user_vault_contract: Any = None
        self._oft_contract: Any = None

    @property
    def live(self) -> bool:
        return self._live

    @property
    def chain_id(self) -> int:
        """The chain this runner submits transactions on. The decision
        loop compares this against each `AllocationTarget.chain_id` to
        decide whether `allocateToStrategy` is the right call or whether
        the target lives on a remote chain that requires the CXR-0a/0b
        bridge pipe."""
        return self._chain_id

    def supports_remote_chain(self, chain_id: int) -> bool:
        """True if `allocateToRemoteStrategy` is wired for `chain_id`.

        Wiring requires an OFT adapter address + an EID map entry for
        the destination chain. Live tx submission additionally needs
        `self._live` — stub mode still records the planned call. The
        decision loop checks this to flip a strategy from defer-mode
        to a real `allocate_to_remote` invocation.
        """
        return (
            bool(self._oft_adapter)
            and chain_id != self._chain_id
            and chain_id in self._remote_chain_eids
        )

    def resolve_remote_vault(self, strategy_id: str) -> str:
        """Return the remote-chain vault address for `strategy_id`.

        For Helios strategyIds the id IS the vault address — so by
        default this round-trips through `Web3.to_checksum_address`.
        Overrides via `remote_vault_overrides` let an operator unwire
        the convention (e.g. point a strategyId at a different
        execution vault) without redeploying.
        """
        sid_lower = strategy_id.lower()
        override = self._remote_vault_overrides.get(sid_lower)
        if override:
            return Web3.to_checksum_address(override)
        return Web3.to_checksum_address(strategy_id)

    @property
    def allocator_vault(self) -> str:
        return self._allocator_vault

    @property
    def allocator_registry(self) -> str:
        return self._allocator_registry

    @property
    def user_vault(self) -> str:
        return self._user_vault

    def allocate(self, user: str, strategy: str, amount: int) -> OnChainCall:
        return self._submit(
            OnChainCall(method="allocateToStrategy", user=user, strategy=strategy, amount=amount)
        )

    def allocate_to_remote(
        self,
        user: str,
        strategy: str,
        amount: int,
        chain_id: int,
        remote_vault: str,
    ) -> OnChainCall:
        """CXR-0c — Send `amount` USDC across the LayerZero OFT bridge to
        `remote_vault` on the chain identified by `chain_id`. Encodes the
        strategyId as bytes32 of the strategy address, mirroring the
        spec's "remote vault address as bytes32" convention.

        Live mode quotes the LZ native fee via `OFT.quoteSend` and passes
        it as `msg.value`. Stub mode records the call with zero fee.
        """
        sid_bytes = bytes.fromhex(Web3.to_checksum_address(strategy)[2:].rjust(64, "0"))
        dst_eid = self._remote_chain_eids.get(chain_id, 0)
        # Floor `amount` to the OFT adapter's shared-decimals base so the
        # adapter's internal `_removeDust` is a no-op. On-chain
        # `AllocatorVault.allocateToRemoteStrategy` hardcodes
        # `minAmountLD == amount`, so any non-zero `amount % 10^12`
        # dust gets stripped by the OFT and tx reverts SlippageExceeded.
        # OFT adapter wraps an 18-dec mUSDC on Kite with sharedDecimals=6,
        # giving a 10^12 conversion rate. Flooring locally keeps the
        # off-chain → on-chain amount agreement intact.
        _CONVERSION = 10**12
        amount -= amount % _CONVERSION
        call = OnChainCall(
            method="allocateToRemoteStrategy",
            user=user,
            strategy=strategy,
            amount=amount,
            dst_eid=dst_eid,
            remote_vault=remote_vault,
            extra_options=_DEFAULT_LZ_EXTRA_OPTIONS,
            strategy_id_bytes32=sid_bytes,
        )
        if amount == 0:
            # After flooring, dust-only amounts collapse to zero. Skip the
            # quote + submit; the loop's `cross_chain.deferred` fallback
            # will pick this up and emit a deferred event instead.
            return self._submit(call)
        if self._live and dst_eid:
            native_fee, lz_token_fee = self._quote_remote_fee(
                dst_eid, remote_vault, user, sid_bytes, amount
            )
            call.lz_native_fee = native_fee
            call.lz_token_fee = lz_token_fee
        return self._submit(call)

    def allocate_to_remote_batch(
        self,
        user: str,
        entries: list[tuple[str, int, str]],
        chain_id: int,
    ) -> OnChainCall:
        """Tier 2 — Batched cross-chain allocate. `entries` is a list of
        `(strategy_id, amount, remote_vault)` tuples sharing a single
        `dst_eid`. Packs N entries into one OFT.send so the ~1 KITE LZ
        V2 fixed fee is amortized across the batch.

        Each entry's amount is floored to the OFT shared-decimals base
        (10^12) so the adapter's `_removeDust` is a no-op. Entries
        whose amount drops to 0 after the floor are filtered out
        upstream by the caller — they'd revert `ZeroAmount` on-chain
        anyway, and burning the LZ fee on a near-dust batch is exactly
        what this lever is meant to avoid.
        """
        dst_eid = self._remote_chain_eids.get(chain_id, 0)
        _CONVERSION = 10**12
        floored: list[tuple[str, int, str]] = []
        sids_hex: list[str] = []
        sid_bytes_list: list[bytes] = []
        amounts: list[int] = []
        vaults: list[str] = []
        for sid, raw_amt, vault in entries:
            amt = int(raw_amt) - (int(raw_amt) % _CONVERSION)
            if amt == 0:
                continue
            floored.append((sid, amt, vault))
            sids_hex.append(sid)
            sid_bytes_list.append(
                bytes.fromhex(Web3.to_checksum_address(sid)[2:].rjust(64, "0"))
            )
            amounts.append(amt)
            vaults.append(Web3.to_checksum_address(vault))

        call = OnChainCall(
            method="allocateToRemoteStrategyBatch",
            user=user,
            strategy=None,
            amount=sum(amounts),
            dst_eid=dst_eid,
            extra_options=_DEFAULT_LZ_EXTRA_OPTIONS,
            batch_strategy_ids=tuple(sids_hex),
            batch_strategy_ids_bytes32=tuple(sid_bytes_list),
            batch_amounts=tuple(amounts),
            batch_remote_vaults=tuple(vaults),
        )
        if not floored or not dst_eid:
            return self._submit(call)
        if self._live:
            native_fee, lz_token_fee = self._quote_remote_fee_batch(
                dst_eid,
                user,
                tuple(sid_bytes_list),
                tuple(amounts),
                tuple(vaults),
            )
            call.lz_native_fee = native_fee
            call.lz_token_fee = lz_token_fee
        return self._submit(call)

    def defund(self, user: str, strategy: str, reason: str) -> OnChainCall:
        return self._submit(
            OnChainCall(method="defundStrategy", user=user, strategy=strategy, reason=reason)
        )

    def rebalance(
        self,
        user: str,
        strategies: list[str],
        weights_bps: list[int],
    ) -> OnChainCall:
        return self._submit(
            OnChainCall(
                method="rebalance",
                user=user,
                strategy=None,
                strategies=tuple(strategies),
                weights_bps=tuple(weights_bps),
            )
        )

    def settle_fee(self, user: str, strategy: str) -> OnChainCall:
        return self._submit(OnChainCall(method="settleStrategyFee", user=user, strategy=strategy))

    # ── Async wrappers ────────────────────────────────────────
    # Each `_submit` ends in `wait_for_transaction_receipt(timeout=30)`.
    # Used directly from the async decision loop, that freezes the event
    # loop — every WS subscriber and the drawdown-poll cadence stall for
    # up to 30s per emitted call. The async variants run the sync path
    # on a worker thread (mirroring `oracle/anchor.AnchorPoster.post_async`)
    # so the loop keeps draining while a single tx waits for its receipt.

    async def allocate_async(self, user: str, strategy: str, amount: int) -> OnChainCall:
        return await asyncio.to_thread(self.allocate, user, strategy, amount)

    async def defund_async(self, user: str, strategy: str, reason: str) -> OnChainCall:
        return await asyncio.to_thread(self.defund, user, strategy, reason)

    async def rebalance_async(
        self,
        user: str,
        strategies: list[str],
        weights_bps: list[int],
    ) -> OnChainCall:
        return await asyncio.to_thread(self.rebalance, user, strategies, weights_bps)

    async def settle_fee_async(self, user: str, strategy: str) -> OnChainCall:
        return await asyncio.to_thread(self.settle_fee, user, strategy)

    async def allocate_to_remote_async(
        self,
        user: str,
        strategy: str,
        amount: int,
        chain_id: int,
        remote_vault: str,
    ) -> OnChainCall:
        return await asyncio.to_thread(
            self.allocate_to_remote, user, strategy, amount, chain_id, remote_vault
        )

    def read_user_vault_balance(self, user: str) -> int | None:
        """Idle UserVault balance for `user`, in raw asset wei.

        Returns None when stub mode is active or `user_vault_address` is
        unset — the loop falls back to its in-memory `delegated_capital_usd`
        in that case (which tests seed manually). Live mode reads
        `UserVault.balanceOf(user)`. The unit is raw asset wei (18 dec
        for the deployed mUSDC mock); `_apply_diffs` passes the same
        units straight to `allocateToStrategy`, so no conversion is
        needed.
        """
        if not self._live or not self._user_vault:
            return None
        self._ensure_live()
        assert self._w3 is not None
        if self._user_vault_contract is None:
            self._user_vault_contract = self._w3.eth.contract(
                address=Web3.to_checksum_address(self._user_vault),
                abi=list(_USER_VAULT_BALANCE_ABI),
            )
        balance = self._user_vault_contract.functions.balanceOf(
            Web3.to_checksum_address(user)
        ).call()
        return int(balance)

    async def read_user_vault_balance_async(self, user: str) -> int | None:
        return await asyncio.to_thread(self.read_user_vault_balance, user)

    def read_strategy_nav_timestamp(self, strategy: str) -> int | None:
        """Return `StrategyVault.lastNAVTimestamp(strategy)` or None in
        stub mode. Used by the loop's candidate refresh to drop
        strategies whose navOracle has gone silent — vaults that look
        `active=true` in the registry but aren't being driven.
        """
        if not self._live:
            return None
        self._ensure_live()
        assert self._w3 is not None
        c = self._w3.eth.contract(
            address=Web3.to_checksum_address(strategy),
            abi=list(_STRATEGY_VAULT_LAST_NAV_ABI),
        )
        try:
            return int(c.functions.lastNAVTimestamp().call())
        except Exception:
            # Phantom addresses (registered without a real contract) or
            # vault layouts without the getter — neither should attract
            # capital, so treat as "never reported".
            return 0

    async def read_strategy_nav_timestamp_async(self, strategy: str) -> int | None:
        return await asyncio.to_thread(self.read_strategy_nav_timestamp, strategy)

    async def read_allocation(self, user: str, strategy: str) -> AllocationState | None:
        """Mirror current on-chain allocation state.

        Stub mode returns None; the loop falls back to its in-memory
        mirror. Live mode reads `AllocatorVault.allocationOf(user, strategy)`.
        """
        if not self._live:
            return None
        self._ensure_live()
        assert self._vault_contract is not None
        record = self._vault_contract.functions.allocationOf(
            Web3.to_checksum_address(user), Web3.to_checksum_address(strategy)
        ).call()
        # Tuple matches IAllocatorVault.AllocationRecord.
        # record[0]=strategy, [1]=capitalDeployed, [2]=highWaterMark,
        # [3]=defundedAt, [4]=lastUpdate.
        capital_deployed = int(record[1])
        hwm = int(record[2])
        defunded_at = int(record[3])
        return AllocationState(
            strategy_id=strategy,
            chain_id=self._chain_id,
            declared_class="",
            capital_deployed_usd=capital_deployed,
            high_water_mark_usd=hwm,
            nav_usd=capital_deployed,  # NAV reads come from StrategyVault, wired in WS4
            last_rebalance_ts=0,
            defunded=defunded_at != 0,
        )

    # ── Allocator registration ───────────────────────────────
    def register_allocator(
        self,
        name: str,
        ranking_function_hash: bytes,
        supported_classes: list[bytes],
        fee_rate_bps: int,
        stake_amount: int,
    ) -> str:
        """One-shot: register this allocator on `AllocatorRegistry`.

        Returns the allocator address (operator vault) registered.
        Stub mode is a no-op returning the configured vault. Live mode
        submits `AllocatorRegistry.registerAllocator(...)` and waits for
        a receipt.

        The reserved-name check (`"Helios Sentinel"` / `"Helios Helix"`)
        is enforced on-chain — registering with a reserved name reverts.
        Third parties spawn this call from `helios-allocator init`'s
        scaffolded `register` command.
        """
        if not self._live:
            _log.info(
                "allocator.onchain.register.dry_run",
                name=name,
                fee_rate_bps=fee_rate_bps,
                stake_amount=stake_amount,
            )
            return self._allocator_vault
        self._ensure_live()
        assert self._w3 is not None
        assert self._account is not None
        if self._registry_contract is None:
            if not self._allocator_registry:
                raise RuntimeError("allocator_registry_address required for register_allocator")
            self._registry_contract = self._w3.eth.contract(
                address=Web3.to_checksum_address(self._allocator_registry),
                abi=IAllocatorRegistry_ABI,
            )
        fn = self._registry_contract.functions.registerAllocator(
            name,
            Web3.to_checksum_address(self._allocator_vault),
            ranking_function_hash,
            supported_classes,
            int(fee_rate_bps),
            int(stake_amount),
        )
        tx = fn.build_transaction(
            {
                "from": self._account.address,
                "nonce": self._w3.eth.get_transaction_count(self._account.address, "pending"),
                "chainId": self._chain_id,
                "gasPrice": self._w3.eth.gas_price,
            }
        )
        signed = self._account.sign_transaction(tx)
        tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt: TxReceipt = self._w3.eth.wait_for_transaction_receipt(
            tx_hash, timeout=RECEIPT_TIMEOUT_SEC
        )
        if receipt["status"] != 1:
            raise RuntimeError(f"registerAllocator reverted: {tx_hash.hex()}")
        _log.info(
            "allocator.onchain.register.submitted",
            name=name,
            tx_hash=tx_hash.hex(),
            block=receipt["blockNumber"],
        )
        return self._allocator_vault

    def _submit(self, call: OnChainCall) -> OnChainCall:
        if not self._live:
            self.pending.append(call)
            _log.info(
                "allocator.onchain.dry_run",
                method=call.method,
                user=call.user,
                strategy=call.strategy,
                amount=call.amount,
                reason=call.reason,
            )
            return call
        try:
            self._send_live(call)
        except Exception as exc:
            call.error = str(exc)
            _log.error(
                "allocator.onchain.submit_failed",
                method=call.method,
                user=call.user,
                strategy=call.strategy,
                err=str(exc),
            )
        # Pending list mirrors *all* attempted calls so `/v1/users/.../events`
        # consumers see the same surface in live + dry modes.
        self.pending.append(call)
        return call

    # ── Live submission ───────────────────────────────────────
    def _ensure_live(self) -> None:
        if self._w3 is not None:
            return
        self._w3 = Web3(Web3.HTTPProvider(self._rpc_url))
        try:
            self._account = Account.from_key(self._operator_pk)
        except Exception as exc:  # pragma: no cover — defensive
            # Don't let the raised value (which may include the malformed key
            # material) propagate up into structlog or a stack trace.
            raise RuntimeError(f"invalid OPERATOR_PK: {type(exc).__name__}") from None
        self._vault_contract = self._w3.eth.contract(
            address=Web3.to_checksum_address(self._allocator_vault),
            # Concat the local `allocateToRemoteStrategy` fragment with
            # the shared interface ABI — see comment above on
            # `_ALLOCATE_TO_REMOTE_ABI`.
            abi=list(IAllocatorVault_ABI) + list(_ALLOCATE_TO_REMOTE_ABI),
        )

    def _send_live(self, call: OnChainCall) -> None:
        self._ensure_live()
        assert self._w3 is not None
        assert self._account is not None
        assert self._vault_contract is not None

        fn = self._build_function(call)
        tx_overrides: dict[str, Any] = {
            "from": self._account.address,
            "nonce": self._w3.eth.get_transaction_count(self._account.address, "pending"),
            "chainId": self._chain_id,
        }
        if (
            call.method in ("allocateToRemoteStrategy", "allocateToRemoteStrategyBatch")
            and call.lz_native_fee
        ):
            tx_overrides["value"] = int(call.lz_native_fee)
        tx = fn.build_transaction(
            {
                **tx_overrides,
                # Anvil + Kite both honour legacy gasPrice; explicit value avoids
                # web3's EIP-1559 fee estimation hitting `eth_feeHistory` which
                # some forks (and our anvil container) don't implement.
                "gasPrice": self._w3.eth.gas_price,
            }
        )
        signed = self._account.sign_transaction(tx)
        tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)
        call.tx_hash = tx_hash.hex()
        receipt: TxReceipt = self._w3.eth.wait_for_transaction_receipt(
            tx_hash, timeout=RECEIPT_TIMEOUT_SEC
        )
        if receipt["status"] != 1:
            raise RuntimeError(f"tx reverted: {call.tx_hash}")
        call.submitted = True
        _log.info(
            "allocator.onchain.submitted",
            method=call.method,
            tx_hash=call.tx_hash,
            block=receipt["blockNumber"],
            gas_used=receipt["gasUsed"],
        )

    def _build_function(self, call: OnChainCall) -> Any:
        assert self._vault_contract is not None
        if call.method == "allocateToStrategy":
            return self._vault_contract.functions.allocateToStrategy(
                Web3.to_checksum_address(call.user),
                Web3.to_checksum_address(_require_strategy(call)),
                int(call.amount),
            )
        if call.method == "defundStrategy":
            return self._vault_contract.functions.defundStrategy(
                Web3.to_checksum_address(call.user),
                Web3.to_checksum_address(_require_strategy(call)),
                call.reason,
            )
        if call.method == "settleStrategyFee":
            return self._vault_contract.functions.settleStrategyFee(
                Web3.to_checksum_address(call.user),
                Web3.to_checksum_address(_require_strategy(call)),
            )
        if call.method == "rebalance":
            return self._vault_contract.functions.rebalance(
                Web3.to_checksum_address(call.user),
                [Web3.to_checksum_address(s) for s in call.strategies],
                [int(w) for w in call.weights_bps],
            )
        if call.method == "allocateToRemoteStrategy":
            # The Sentinel-facing tuple is (nativeFee, lzTokenFee); web3.py
            # auto-encodes the named struct from this ordered pair.
            return self._vault_contract.functions.allocateToRemoteStrategy(
                Web3.to_checksum_address(call.user),
                call.strategy_id_bytes32,
                int(call.amount),
                int(call.dst_eid),
                Web3.to_checksum_address(call.remote_vault),
                call.extra_options,
                (int(call.lz_native_fee), int(call.lz_token_fee)),
            )
        if call.method == "allocateToRemoteStrategyBatch":
            # Tier 2 — single-struct RemoteBatchParams tuple. Solidity-side
            # field order: (user, strategyIds, amounts, remoteVaults,
            # dstEid, extraOptions, lzFee). web3.py auto-encodes from the
            # ordered Python tuple.
            params_tuple = (
                Web3.to_checksum_address(call.user),
                [bytes(b) for b in call.batch_strategy_ids_bytes32],
                [int(a) for a in call.batch_amounts],
                [Web3.to_checksum_address(v) for v in call.batch_remote_vaults],
                int(call.dst_eid),
                call.extra_options,
                (int(call.lz_native_fee), int(call.lz_token_fee)),
            )
            return self._vault_contract.functions.allocateToRemoteStrategyBatch(params_tuple)
        raise ValueError(f"unknown onchain method: {call.method}")

    def _quote_remote_fee(
        self,
        dst_eid: int,
        remote_vault: str,
        user: str,
        sid_bytes: bytes,
        amount: int,
    ) -> tuple[int, int]:
        """Return (nativeFee, lzTokenFee) from `OFT.quoteSend`.

        We rebuild the same `SendParam` shape the AllocatorVault will
        encode at execution time — to → `destinationReceiver[dstEid]`,
        composeMsg → `(action=0, sid, vault, user)`. We don't read the
        on-chain `destinationReceiver` slot here; the OFT only uses
        `to` for fee calculation, and any non-zero bytes32 produces the
        same quote — so we pass `bytes32(remote_vault)` directly to
        keep the call self-contained.
        """
        self._ensure_oft_live()
        assert self._w3 is not None
        assert self._oft_contract is not None
        compose_msg = self._w3.codec.encode(
            ["uint8", "bytes32", "address", "address"],
            [
                _CXR_ACTION_ALLOCATE,
                sid_bytes,
                Web3.to_checksum_address(remote_vault),
                Web3.to_checksum_address(user),
            ],
        )
        to_bytes32 = bytes.fromhex(
            Web3.to_checksum_address(remote_vault)[2:].rjust(64, "0")
        )
        send_param = (
            int(dst_eid),
            to_bytes32,
            int(amount),
            int(amount),
            _DEFAULT_LZ_EXTRA_OPTIONS,
            compose_msg,
            b"",
        )
        result = self._oft_contract.functions.quoteSend(send_param, False).call()
        return int(result[0]), int(result[1])

    def _quote_remote_fee_batch(
        self,
        dst_eid: int,
        user: str,
        sid_bytes_list: tuple[bytes, ...],
        amounts: tuple[int, ...],
        remote_vaults: tuple[str, ...],
    ) -> tuple[int, int]:
        """Tier 2 — Quote LZ V2 native fee for a batched compose. Mirrors
        the AllocatorVault's batch payload shape so the fee matches what
        the actual submit will burn.
        """
        self._ensure_oft_live()
        assert self._w3 is not None
        assert self._oft_contract is not None
        compose_msg = self._w3.codec.encode(
            ["uint8", "bytes32[]", "uint256[]", "address[]", "address"],
            [
                _CXR_ACTION_ALLOCATE_BATCH,
                list(sid_bytes_list),
                list(amounts),
                [Web3.to_checksum_address(v) for v in remote_vaults],
                Web3.to_checksum_address(user),
            ],
        )
        total = sum(amounts)
        # `to` in SendParam is the destinationReceiver; the OFT fee
        # quote doesn't depend on its exact value (any non-zero bytes32
        # produces the same quote), so we pass a placeholder bytes32.
        # Matches the single-call `_quote_remote_fee` convention.
        to_bytes32 = bytes.fromhex(
            Web3.to_checksum_address(remote_vaults[0])[2:].rjust(64, "0")
        )
        send_param = (
            int(dst_eid),
            to_bytes32,
            int(total),
            int(total),
            _DEFAULT_LZ_EXTRA_OPTIONS,
            compose_msg,
            b"",
        )
        result = self._oft_contract.functions.quoteSend(send_param, False).call()
        return int(result[0]), int(result[1])

    def _ensure_oft_live(self) -> None:
        self._ensure_live()
        if self._oft_contract is not None:
            return
        if not self._oft_adapter:
            raise RuntimeError("oft_adapter_address not configured")
        assert self._w3 is not None
        self._oft_contract = self._w3.eth.contract(
            address=Web3.to_checksum_address(self._oft_adapter),
            abi=list(_OFT_QUOTE_SEND_ABI),
        )


def _require_strategy(call: OnChainCall) -> str:
    if not call.strategy:
        raise ValueError(f"{call.method} requires a strategy address")
    return call.strategy


__all__ = ["AllocatorOnChain", "OnChainCall"]
