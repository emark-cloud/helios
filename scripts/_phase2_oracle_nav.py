"""WS6 PR3.A — oracle anchor cadence + NAV trajectory helpers.

Two e2e helpers that the Phase 2 scenario orchestrator drives between
trade emission and reputation scoring:

  1. `OracleAnchorDriver` — synthesizes a sequence of EIP-712-signed
     `OraclePriceCommit` / `OracleYieldCommit` payloads at a fixed
     bar cadence (default = 1 commit per 10 bars across the 90d
     compressed window). Roots are deterministic Poseidon-style
     placeholders — the on-chain anchor only checks signature recovery
     and window monotonicity, it never inspects the root preimage.

  2. `NavTrajectoryDriver` — synthesizes a per-strategy daily NAV
     curve over 30 daily samples ending at `synthetic_now`. Each
     curve is signed exactly the way `StrategyVault.reportNAV`
     verifies — EIP-712 typed data over `NAVUpdate(uint256 totalNAV,
     uint64 timestamp)` under domain `(HeliosStrategyVault, "1",
     chainId, verifyingContract=vault)`; v ∈ {27,28}.

The trajectories are deliberately diverging across the 6 vaults so
the §8.2 reputation engine produces non-trivially-different scores
within each cohort: primary momentum smoothly trends, variant2
peaks then craters (heavy 90d drawdown), mean-rev primary chops
upward, mean-rev variant2 stays flat, YR primary slowly gains,
YR variant2 mildly declines. Risk + perf components are the
designated differentiators; stake + age + proof are equal across
the cohort by construction (all 6 share 5k stake + a single
attested proof).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from eth_abi.abi import encode as abi_encode
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils.crypto import keccak
from web3 import Web3
from web3.contract.contract import Contract

# 200 simulated bars compressed into a 90-day window. One bar = 90/200 days.
BARS_PER_WINDOW = 200
ANCHOR_BARS_PER_COMMIT = 10
ANCHOR_COMMITS_PER_ANCHOR = BARS_PER_WINDOW // ANCHOR_BARS_PER_COMMIT  # = 20
DAY_SEC = 24 * 60 * 60
NAV_SAMPLES_PER_VAULT = 30  # one daily sample over the 30d window


# ── Oracle anchor cadence ───────────────────────────────────────


@dataclass(frozen=True, slots=True)
class _OracleCommit:
    root: bytes
    window_start: int
    window_end: int


def _synthetic_root(seed: bytes, idx: int) -> bytes:
    """Non-zero deterministic 32-byte placeholder.

    The anchor rejects `bytes32(0)` and dedupes on root, so each commit
    needs a fresh non-zero value. We don't run the real Poseidon ring
    here — that's the off-chain oracle's job in production. The
    e2e is exercising the *cadence* and signature path only.
    """
    return keccak(seed + idx.to_bytes(8, "big"))


def _commits_for_anchor(
    *,
    seed: bytes,
    base_ts_sec: int,
    bar_window_sec: int,
) -> list[_OracleCommit]:
    """Build `ANCHOR_COMMITS_PER_ANCHOR` non-overlapping windows.

    Each window covers `ANCHOR_BARS_PER_COMMIT * bar_window_sec` seconds,
    in **milliseconds** per `OraclePriceAnchor` semantics ("oracle
    internal clock, ms"). Monotonicity is enforced by adjacency:
    `windowStart_n = windowEnd_{n-1}`.
    """
    out: list[_OracleCommit] = []
    bar_window_ms = bar_window_sec * 1_000
    base_ts_ms = base_ts_sec * 1_000
    for i in range(ANCHOR_COMMITS_PER_ANCHOR):
        ws = base_ts_ms + i * ANCHOR_BARS_PER_COMMIT * bar_window_ms
        we = ws + ANCHOR_BARS_PER_COMMIT * bar_window_ms
        out.append(
            _OracleCommit(
                root=_synthetic_root(seed, i),
                window_start=ws,
                window_end=we,
            )
        )
    return out


def _sign_oracle_commit(
    *,
    domain_name: str,
    chain_id: int,
    anchor_address: str,
    root: bytes,
    window_start: int,
    window_end: int,
    nonce: int,
    signer_pk: str,
) -> bytes:
    domain = {
        "name": domain_name,
        "version": "1",
        "chainId": chain_id,
        "verifyingContract": Web3.to_checksum_address(anchor_address),
    }
    types = {
        "Oracle" + ("Price" if "Price" in domain_name else "Yield") + "Commit": [
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
    account = Account.from_key(signer_pk)
    return bytes(account.sign_message(encoded).signature)


@dataclass
class OracleAnchorDriver:
    """Posts `ANCHOR_COMMITS_PER_ANCHOR` price + yield commits to the
    deployed `OraclePriceAnchor` and `OracleYieldAnchor`.

    Both anchors share the same signer (deployer in the e2e), the same
    nonce stream (per-anchor — auto-increments inside the contract),
    and an identical 90d / 200-bar cadence. The price anchor's root
    seed differs from the yield anchor's so any future tooling that
    keys off `root` can disambiguate between them.
    """

    w3: Web3
    chain_id: int
    signer_pk: str
    price_anchor: Contract
    yield_anchor: Contract
    base_ts_sec: int  # synthetic now - 90 days
    bar_window_sec: int = (90 * DAY_SEC) // BARS_PER_WINDOW  # ~38_880s

    def drive(
        self,
        send: Any,  # _send (from e2e_scenario_phase2 module)
        deployer: Any,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        price_receipts: list[dict[str, Any]] = []
        yield_receipts: list[dict[str, Any]] = []
        price_commits = _commits_for_anchor(
            seed=b"helios.oracle.price",
            base_ts_sec=self.base_ts_sec,
            bar_window_sec=self.bar_window_sec,
        )
        yield_commits = _commits_for_anchor(
            seed=b"helios.oracle.yield",
            base_ts_sec=self.base_ts_sec,
            bar_window_sec=self.bar_window_sec,
        )
        # Read each anchor's starting nonce and walk forward; the
        # contract refuses any signature whose embedded nonce diverges
        # from its internal counter.
        price_nonce = self.price_anchor.functions.nonce().call()
        yield_nonce = self.yield_anchor.functions.nonce().call()
        for i, c in enumerate(price_commits):
            sig = _sign_oracle_commit(
                domain_name="HeliosOraclePriceAnchor",
                chain_id=self.chain_id,
                anchor_address=self.price_anchor.address,
                root=c.root,
                window_start=c.window_start,
                window_end=c.window_end,
                nonce=price_nonce + i,
                signer_pk=self.signer_pk,
            )
            r = send(
                self.w3,
                deployer,
                self.price_anchor.functions.commit(c.root, c.window_start, c.window_end, sig),
            )
            price_receipts.append(r)
        for i, c in enumerate(yield_commits):
            sig = _sign_oracle_commit(
                domain_name="HeliosOracleYieldAnchor",
                chain_id=self.chain_id,
                anchor_address=self.yield_anchor.address,
                root=c.root,
                window_start=c.window_start,
                window_end=c.window_end,
                nonce=yield_nonce + i,
                signer_pk=self.signer_pk,
            )
            r = send(
                self.w3,
                deployer,
                self.yield_anchor.functions.commit(c.root, c.window_start, c.window_end, sig),
            )
            yield_receipts.append(r)
        return price_receipts, yield_receipts


# ── NAV trajectory cadence ──────────────────────────────────────


# 6 NAV trajectories — one per vault key. Each is a list of (day_offset,
# nav_e6) pairs spanning [-29, 0] (oldest first). All start at 5_000 USDC
# = 5_000 * 1e6, the per-strategy capital allocation. The cohort math
# at §8.2 only needs windowed Sharpe + drawdown, so the absolute units
# don't matter — divergence patterns do.
#
# Notation: MOM_PRIM trends smoothly upward (+30%), MOM_V2 climbs then
# crashes (heavy drawdown), MR_PRIM chops upward (modest Sharpe),
# MR_V2 stays flat (~zero Sharpe), YR_PRIM gains slowly (positive),
# YR_V2 declines slowly (negative perf).


# Deterministic per-day noise term (units: USDC e6). Without this, a
# pure geometric curve has identical log-returns every day, var=0,
# and `annualized_sharpe_from_nav` returns 0.0 — collapsing perf to
# zero for any "smooth" trajectory and breaking within-class divergence.
def _det_noise(d: int) -> int:
    return ((d * 7919) % 11) * 100_000  # 0..1M USDC, dwarfed by drift


def _nav_curve_smooth_up(start_e6: int, drift_per_day: float, days: int) -> list[int]:
    return [int(start_e6 * (1.0 + drift_per_day) ** d) + _det_noise(d) for d in range(days)]


def _nav_curve_pump_dump(
    start_e6: int, peak_factor: float, trough_factor: float, days: int
) -> list[int]:
    half = days // 2
    out: list[int] = []
    for d in range(days):
        if d <= half:
            f = 1.0 + (peak_factor - 1.0) * (d / half)
        else:
            # Linear collapse from peak to trough over the back half.
            f = peak_factor - (peak_factor - trough_factor) * ((d - half) / (days - 1 - half))
        out.append(int(start_e6 * f))
    return out


def _nav_curve_choppy(start_e6: int, drift: float, chop_e6: int, days: int) -> list[int]:
    out: list[int] = []
    for d in range(days):
        sign = 1 if d % 2 == 0 else -1
        out.append(int(start_e6 * (1.0 + drift) ** d) + sign * chop_e6)
    return out


def _nav_curve_flat(start_e6: int, jitter_e6: int, days: int) -> list[int]:
    return [start_e6 + (1 if d % 2 == 0 else -1) * jitter_e6 for d in range(days)]


# Map vault role → trajectory. Vault role is the canonical key from
# `_STRATEGY_VAULT_KEYS` in `e2e_scenario_phase2.py`.
def trajectory_for(vault_role: str, days: int = NAV_SAMPLES_PER_VAULT) -> list[int]:
    start = 5_000 * 10**6  # 5k USDC
    if vault_role == "strategyVaultMomentum":
        return _nav_curve_smooth_up(start, 0.0089, days)  # +30% over 30d
    if vault_role == "strategyVaultMomentumVariant2":
        return _nav_curve_pump_dump(start, 1.16, 0.84, days)  # +16% then -28%
    if vault_role == "strategyVaultMeanReversion":
        return _nav_curve_choppy(start, 0.0030, 50_000, days)  # +9% with chop
    if vault_role == "strategyVaultMeanReversionVariant2":
        return _nav_curve_flat(start, 30_000, days)  # flat ± $30
    if vault_role == "strategyVaultYieldRotation":
        return _nav_curve_smooth_up(start, 0.0026, days)  # +8% over 30d
    if vault_role == "strategyVaultYieldRotationVariant2":
        return _nav_curve_smooth_up(start, -0.0020, days)  # -6% over 30d
    raise ValueError(f"unknown vault role: {vault_role!r}")


def _sign_nav(
    *,
    chain_id: int,
    vault_address: str,
    total_nav: int,
    timestamp: int,
    signer_pk: str,
) -> bytes:
    """Match `StrategyVault.reportNAV` — EIP-712 typed data over
    `NAVUpdate(uint256 totalNAV, uint64 timestamp)` under domain
    `(name="HeliosStrategyVault", version="1", chainId,
    verifyingContract=vault)`. eth_account.sign_message produces a
    65-byte signature with v ∈ {27,28}, which is what OZ ECDSA.recover
    expects."""
    domain = {
        "name": "HeliosStrategyVault",
        "version": "1",
        "chainId": chain_id,
        "verifyingContract": Web3.to_checksum_address(vault_address),
    }
    types = {
        "NAVUpdate": [
            {"name": "totalNAV", "type": "uint256"},
            {"name": "timestamp", "type": "uint64"},
        ]
    }
    message = {"totalNAV": total_nav, "timestamp": timestamp}
    encoded = encode_typed_data(domain_data=domain, message_types=types, message_data=message)
    pk = signer_pk[2:] if signer_pk.startswith("0x") else signer_pk
    return bytes(Account.from_key(bytes.fromhex(pk)).sign_message(encoded).signature)


def encode_signed_nav(
    *,
    chain_id: int,
    vault_address: str,
    total_nav: int,
    timestamp: int,
    signer_pk: str,
) -> bytes:
    sig = _sign_nav(
        chain_id=chain_id,
        vault_address=vault_address,
        total_nav=total_nav,
        timestamp=timestamp,
        signer_pk=signer_pk,
    )
    return abi_encode(["uint256", "uint64", "bytes"], [total_nav, timestamp, sig])


@dataclass
class NavTrajectoryDriver:
    """Drives `StrategyVault.reportNAV(...)` across all 6 vaults.

    For each vault, posts `NAV_SAMPLES_PER_VAULT` NAV updates, one per
    simulated day, oldest first (the contract enforces strictly-
    increasing `timestamp`). The signer is the deployer = navOracle
    (set in `DeployPhase1.s.sol::_deployStrategyVault`).
    """

    w3: Web3
    chain_id: int
    signer_pk: str
    synthetic_now_sec: int

    def drive(
        self,
        send: Any,
        deployer: Any,
        vaults_by_role: dict[str, Contract],
    ) -> dict[str, list[dict[str, Any]]]:
        """Returns receipts per vault role for assertion sanity checks."""
        receipts: dict[str, list[dict[str, Any]]] = {}
        for role, vault in vaults_by_role.items():
            curve = trajectory_for(role)
            role_receipts: list[dict[str, Any]] = []
            # Oldest sample first; each sample is one day apart, ending
            # at synthetic_now_sec.
            for i, total_nav in enumerate(curve):
                ts = self.synthetic_now_sec - (NAV_SAMPLES_PER_VAULT - 1 - i) * DAY_SEC
                signed = encode_signed_nav(
                    chain_id=self.chain_id,
                    vault_address=vault.address,
                    total_nav=total_nav,
                    timestamp=ts,
                    signer_pk=self.signer_pk,
                )
                r = send(self.w3, deployer, vault.functions.reportNAV(signed))
                role_receipts.append(r)
            receipts[role] = role_receipts
        return receipts


__all__ = [
    "ANCHOR_COMMITS_PER_ANCHOR",
    "BARS_PER_WINDOW",
    "DAY_SEC",
    "NAV_SAMPLES_PER_VAULT",
    "NavTrajectoryDriver",
    "OracleAnchorDriver",
    "encode_signed_nav",
    "trajectory_for",
]
