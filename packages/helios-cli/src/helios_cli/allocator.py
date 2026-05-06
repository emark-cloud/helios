"""Allocator operator commands.

`init` scaffolds a project from the bundled template (WS2.A). `backtest`,
`simulate`, `stake`, `deploy`, and `logs` are the day-to-day surface
once the project exists (WS2.B). Heavy lifting (web3 calls, SSH, dynamic
import) lives in module-level helpers so smoke tests can monkeypatch.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer
from helios_allocator.backtest import (
    BacktestConfig,
    StrategyNavSeries,
    parse_period,
    render_markdown,
    run_backtest,
)
from helios_allocator.types import MetaStrategy, StrategyCandidate
from rich.console import Console
from rich.table import Table
from web3 import Web3

app = typer.Typer(help="Allocator operator commands", no_args_is_help=True)
stake_app = typer.Typer(help="AllocatorRegistry stake management", no_args_is_help=True)
app.add_typer(stake_app, name="stake")
console = Console()


_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates" / "allocator"

# `Helios *` is reserved for first-party reference brands. The on-chain
# `AllocatorRegistry` constructor pre-seeds the production names; we
# fail fast client-side so operators don't burn a tx on a guaranteed
# revert.
_RESERVED_NAMESPACE = re.compile(r"^helios\b", re.IGNORECASE)


# ─── init ──────────────────────────────────────────────────


@app.command()
def init(
    name: str = typer.Option(
        ...,
        help='Allocator name. The "Helios *" namespace is reserved for reference brands.',
    ),
    target_dir: Path = typer.Option(
        Path("./my-allocator"),
        help="Directory to scaffold into. Created if missing.",
    ),
    force: bool = typer.Option(
        False, "--force", help="Overwrite the target directory if it already exists."
    ),
) -> None:
    """Scaffold a new allocator project from the SDK template."""
    name = name.strip()
    if not name:
        raise typer.BadParameter("--name must be a non-empty string.", param_hint="--name")
    if _RESERVED_NAMESPACE.match(name):
        raise typer.BadParameter(
            f'"{name}" is in the reserved "Helios *" namespace. '
            'Pick a different name (e.g. "Acme Allocator").',
            param_hint="--name",
        )

    name_snake = _to_snake(name)
    name_pascal = _to_pascal(name)
    name_kebab = name_snake.replace("_", "-")
    if not name_snake or not name_snake.isidentifier():
        raise typer.BadParameter(
            f"--name {name!r} produces snake_case {name_snake!r} which is not a "
            "valid Python identifier. Use ASCII letters, digits, and spaces.",
            param_hint="--name",
        )

    target = target_dir.resolve()
    if target.exists():
        if not force:
            raise typer.BadParameter(
                f"target {target} already exists; pass --force to overwrite.",
                param_hint="--target-dir",
            )
        shutil.rmtree(target)

    if not _TEMPLATE_DIR.exists():
        raise typer.BadParameter(f"template missing at {_TEMPLATE_DIR}; reinstall helios-cli.")

    substitutions = {
        "{{NAME}}": name,
        "{{NAME_PASCAL}}": name_pascal,
        "{{NAME_SNAKE}}": name_snake,
        "{{NAME_KEBAB}}": name_kebab,
    }
    _render_tree(_TEMPLATE_DIR, target, substitutions, name_snake)

    console.print(f"[green]Scaffolded[/green] [bold]{name}[/bold] at {target}")
    console.print(
        "Next: cp .env.example .env, fill in keys, then "
        f"`pip install -e {target}` and `python -m {name_snake}`."
    )


def _render_tree(
    src: Path,
    dst: Path,
    substitutions: dict[str, str],
    name_snake: str,
) -> None:
    """Walk `src`, render each file/dir into `dst`."""
    for entry in sorted(src.rglob("*")):
        rel = entry.relative_to(src)
        rendered_parts = [name_snake if part == "__name_snake__" else part for part in rel.parts]
        out = dst.joinpath(*rendered_parts)
        if entry.is_dir():
            out.mkdir(parents=True, exist_ok=True)
            continue
        if out.suffix == ".tmpl":
            out = out.with_suffix("")
        out.parent.mkdir(parents=True, exist_ok=True)
        text = entry.read_text(encoding="utf-8")
        for needle, replacement in substitutions.items():
            text = text.replace(needle, replacement)
        out.write_text(text, encoding="utf-8")


def _to_snake(name: str) -> str:
    """`"Test ThirdParty"` → `"test_third_party"`."""
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    parts = re.split(r"[^A-Za-z0-9]+", spaced)
    return "_".join(p.lower() for p in parts if p)


def _to_pascal(name: str) -> str:
    """`"test third-party"` → `"TestThirdParty"`."""
    parts = re.split(r"[^A-Za-z0-9]+", name)
    return "".join(p[:1].upper() + p[1:] for p in parts if p)


# ─── allocator class loader ────────────────────────────────

_ALLOCATOR_REF_RE = re.compile(r"^(?P<path>[^:]+):(?P<cls>\w+)$")


def _load_allocator(ref: str) -> Any:
    """Resolve `path/to/module.py:ClassName` or `pkg.mod:ClassName` →
    instance of the BaseAllocator subclass.

    Tests monkeypatch this to inject a stub instance.
    """
    m = _ALLOCATOR_REF_RE.match(ref.strip())
    if not m:
        raise typer.BadParameter(
            f"--allocator must look like 'path/to/module.py:ClassName' or "
            f"'pkg.mod:ClassName', got {ref!r}.",
            param_hint="--allocator",
        )
    path_part = m.group("path")
    cls_name = m.group("cls")
    path = Path(path_part)
    if path.exists() and path.suffix == ".py":
        spec = importlib.util.spec_from_file_location(path.stem, path)
        if spec is None or spec.loader is None:
            raise typer.BadParameter(f"could not load module from {path}.")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    else:
        try:
            module = importlib.import_module(path_part)
        except ImportError as e:
            raise typer.BadParameter(f"could not import {path_part!r}: {e}") from e
    cls = getattr(module, cls_name, None)
    if cls is None:
        raise typer.BadParameter(f"{path_part}:{cls_name} not found.")
    return cls()


# ─── backtest ──────────────────────────────────────────────


@app.command()
def backtest(
    allocator_ref: str = typer.Option(
        ...,
        "--allocator",
        help="Allocator reference: 'path/to/module.py:ClassName' or 'pkg.mod:ClassName'.",
    ),
    capital: int = typer.Option(50_000, help="Starting capital in USDC"),
    period: str = typer.Option("90d", help="Backtest period, e.g. 30d / 3m / 1y"),
    output: Path | None = typer.Option(None, help="Write the markdown report here."),
    fixture: Path | None = typer.Option(
        None,
        help=(
            "Optional JSON of pre-fetched StrategyNavSeries inputs. "
            "If omitted, the runner pulls from Goldsky via $GOLDSKY_ENDPOINT."
        ),
    ),
) -> None:
    """Backtest an allocator against historical strategy P&L."""
    allocator = _load_allocator(allocator_ref)
    parse_period(period)  # Validate the period string before going any further.
    strategies = _load_backtest_strategies(fixture)
    if not strategies:
        raise typer.BadParameter(
            "no strategy NAV traces available — pass --fixture or set GOLDSKY_ENDPOINT.",
            param_hint="--fixture",
        )
    cfg = BacktestConfig(capital=capital, period=period)
    report = run_backtest(allocator, strategies, cfg)
    _render_backtest_summary(report)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(render_markdown(report), encoding="utf-8")
        console.print(f"[green]Wrote[/green] markdown report → {output}")


def _load_backtest_strategies(fixture: Path | None) -> list[Any]:
    """Resolve strategy NAV traces from fixture or live Goldsky.

    Tests monkeypatch this to short-circuit Goldsky.
    """
    if fixture is not None:
        raw = json.loads(fixture.read_text(encoding="utf-8"))
        return [StrategyNavSeries(**row) for row in raw]
    # No fixture and no live mode is intentional in WS2.B — the live
    # path requires a running subgraph and is exercised end-to-end in
    # WS7. Returning an empty list lets the CLI surface a clear error
    # rather than silently producing a zero-strategy report.
    return []


def _render_backtest_summary(report: Any) -> None:
    s = report.summary_dict()
    table = Table(title=f"Backtest — {s['allocator_name']}", show_lines=False)
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    table.add_row("Starting capital", f"${s['capital']:,}")
    table.add_row("Final NAV", f"${s['final_nav']:,.2f}")
    table.add_row("Total return", f"{s['total_return_pct']:+.2f}%")
    table.add_row("Sharpe (annualised)", f"{s['sharpe']:+.2f}")
    table.add_row("Max drawdown", f"{s['max_drawdown_pct']:.2f}%")
    table.add_row("Allocator fees paid", f"${s['allocator_fees_paid']:,.2f}")
    table.add_row("Period", f"{s['period']} ({s['period_days']} days)")
    console.print(table)


# ─── simulate ──────────────────────────────────────────────


@app.command()
def simulate(
    allocator_ref: str = typer.Option(..., "--allocator"),
    users: int = typer.Option(100, help="Number of synthetic users"),
    seed: int = typer.Option(42, help="RNG seed for reproducibility"),
) -> None:
    """Sweep N synthetic users through the allocator's rank + allocate
    pipeline. Prints aggregate stats.

    Useful for tuning fee/correlation thresholds against typical user
    populations before live deploy.
    """
    allocator = _load_allocator(allocator_ref)
    rng = random.Random(seed)
    candidates = _synthetic_universe(StrategyCandidate, n=12, rng=rng)

    fills_by_strategy: dict[str, int] = {c.strategy_id: 0 for c in candidates}
    total_capital = 0
    n_targets = 0
    for _ in range(users):
        user = _synthetic_user(MetaStrategy, rng)
        scores = allocator.rank_strategies(user, candidates)
        ranked = [c for _, c in sorted(zip(scores, candidates, strict=True), key=lambda p: -p[0])]
        targets = allocator.allocate(user, ranked, user.max_capital_usd)
        n_targets += len(targets)
        for t in targets:
            fills_by_strategy[t.strategy_id] += 1
            total_capital += t.capital_usd

    table = Table(title=f"Simulate — {users} synthetic users", show_lines=False)
    table.add_column("Strategy", style="bold")
    table.add_column("Times picked", justify="right")
    for sid, fills in sorted(fills_by_strategy.items(), key=lambda kv: -kv[1]):
        table.add_row(sid, str(fills))
    console.print(table)
    console.print(
        f"Total capital deployed across simulated users: ${total_capital:,}; "
        f"avg targets per user: {n_targets / max(1, users):.2f}"
    )


def _synthetic_universe(cls: Any, n: int, rng: random.Random) -> list[Any]:
    classes = ("momentum_v1", "mean_reversion_v1", "yield_rotation_v1")
    out: list[Any] = []
    for i in range(n):
        out.append(
            cls(
                strategy_id=f"0xsim{i:04x}",
                declared_class=classes[i % len(classes)],
                chain_id=2368,
                operator="0x" + "0" * 39 + str(i % 10),
                fee_rate_bps=rng.choice([300, 500, 1_000, 1_500, 2_000]),
                stake_amount_usd=rng.randint(2_000, 20_000),
                max_capacity_usd=rng.randint(50_000, 500_000),
                current_allocations_usd=rng.randint(0, 30_000),
                reputation_score=round(rng.uniform(0.1, 0.95), 4),
                realized_volatility_30d=round(rng.uniform(0.05, 0.6), 4),
                sharpe_30d=round(rng.uniform(-1.0, 2.5), 4),
                max_drawdown_30d_bps=rng.randint(200, 4_500),
                trades_attested=rng.randint(50, 1_000),
            )
        )
    return out


def _synthetic_user(cls: Any, rng: random.Random) -> Any:
    return cls(
        user_address="0x" + "".join(rng.choice("0123456789abcdef") for _ in range(40)),
        allowed_strategy_classes=("momentum_v1", "mean_reversion_v1", "yield_rotation_v1"),
        allowed_assets=("USDC", "WKITE", "WETH"),
        allowed_chains=(2368,),
        max_capital_usd=rng.choice([10_000, 25_000, 50_000, 100_000]),
        max_per_strategy_bps=rng.choice([2_500, 4_000, 5_000]),
        max_strategies_count=rng.randint(3, 7),
        drawdown_threshold_bps=rng.choice([1_500, 2_000, 2_500, 3_000]),
        max_fee_rate_bps=rng.choice([1_500, 2_000, 2_500, 3_000]),
        rebalance_cadence_sec=86_400,
        valid_until=2**63 - 1,
    )


# ─── stake ─────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class StakeContext:
    """Fields every stake command needs. `_make_stake_context` builds
    one from CLI inputs + env vars; tests substitute a fake."""

    rpc_url: str
    operator_pk: str
    allocator_id: str
    registry_address: str


def _make_stake_context(
    allocator_id: str,
    rpc_url: str | None,
    operator_pk: str | None,
    registry_address: str | None,
) -> StakeContext:
    """Resolve required inputs from flags + environment.

    Uses the deployment file as the canonical registry address when
    `--registry` is not passed.
    """
    rpc = rpc_url or os.environ.get("KITE_RPC_URL", "")
    pk = operator_pk or os.environ.get("ALLOCATOR_OPERATOR_PK", "")
    registry = registry_address or os.environ.get("ALLOCATOR_REGISTRY", "")
    if not rpc:
        raise typer.BadParameter("set --rpc-url or KITE_RPC_URL.", param_hint="--rpc-url")
    if not pk:
        raise typer.BadParameter(
            "set --operator-pk or ALLOCATOR_OPERATOR_PK.", param_hint="--operator-pk"
        )
    if not registry:
        raise typer.BadParameter("set --registry or ALLOCATOR_REGISTRY.", param_hint="--registry")
    return StakeContext(
        rpc_url=rpc, operator_pk=pk, allocator_id=allocator_id, registry_address=registry
    )


def _send_stake_tx(ctx: StakeContext, fn_name: str, args: list[Any]) -> str:
    """Build, sign, and submit an `AllocatorRegistry.<fn_name>(*args)` tx.

    Returns the tx hash. Tests monkeypatch this to short-circuit web3.
    """
    w3 = Web3(Web3.HTTPProvider(ctx.rpc_url))
    abi = _allocator_registry_abi()
    contract = w3.eth.contract(address=Web3.to_checksum_address(ctx.registry_address), abi=abi)
    account = w3.eth.account.from_key(ctx.operator_pk)
    fn = getattr(contract.functions, fn_name)(*args)
    tx = fn.build_transaction(
        {
            "from": account.address,
            "nonce": w3.eth.get_transaction_count(account.address),
            "chainId": w3.eth.chain_id,
            "gas": 400_000,
        }
    )
    signed = account.sign_transaction(tx)
    raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction  # web3 v6/v7
    tx_hash = w3.eth.send_raw_transaction(raw)
    return tx_hash.hex()


def _read_stake_state(ctx: StakeContext) -> dict[str, Any]:
    """Read `allocatorOf` + `pendingWithdrawals` for a balance check.

    Tests monkeypatch this to return a fixed dict.
    """
    w3 = Web3(Web3.HTTPProvider(ctx.rpc_url))
    abi = _allocator_registry_abi()
    contract = w3.eth.contract(address=Web3.to_checksum_address(ctx.registry_address), abi=abi)
    aid = Web3.to_checksum_address(ctx.allocator_id)
    entry = contract.functions.allocatorOf(aid).call()
    pending = contract.functions.pendingWithdrawals(aid).call()
    return {
        "stakeAmount": int(entry[5]) if len(entry) > 5 else 0,
        "active": bool(entry[7]) if len(entry) > 7 else False,
        "pendingAmount": int(pending[0]),
        "unlockAt": int(pending[1]),
    }


def _allocator_registry_abi() -> list[dict[str, Any]]:
    """Minimal ABI fragments for stake operations. Sourced from the
    `AllocatorRegistry.sol` interface; full ABI lives in
    `packages/contracts-abi`. Inlined here so the CLI ships without a
    workspace runtime dep on the abi package."""
    return [
        {
            "type": "function",
            "name": "topUpStake",
            "stateMutability": "nonpayable",
            "inputs": [
                {"name": "allocatorId", "type": "address"},
                {"name": "amount", "type": "uint256"},
            ],
            "outputs": [],
        },
        {
            "type": "function",
            "name": "initiateStakeWithdrawal",
            "stateMutability": "nonpayable",
            "inputs": [
                {"name": "allocatorId", "type": "address"},
                {"name": "amount", "type": "uint256"},
            ],
            "outputs": [],
        },
        {
            "type": "function",
            "name": "completeStakeWithdrawal",
            "stateMutability": "nonpayable",
            "inputs": [{"name": "allocatorId", "type": "address"}],
            "outputs": [],
        },
        {
            "type": "function",
            "name": "allocatorOf",
            "stateMutability": "view",
            "inputs": [{"name": "allocatorId", "type": "address"}],
            "outputs": [
                {
                    "name": "",
                    "type": "tuple",
                    "components": [
                        {"name": "name", "type": "string"},
                        {"name": "operator", "type": "address"},
                        {"name": "operatorVault", "type": "address"},
                        {"name": "rankingFunctionHash", "type": "bytes32"},
                        {"name": "supportedClasses", "type": "uint256[]"},
                        {"name": "stakeAmount", "type": "uint256"},
                        {"name": "feeRateBps", "type": "uint256"},
                        {"name": "active", "type": "bool"},
                        {"name": "registeredAt", "type": "uint64"},
                        {"name": "isReferenceBrand", "type": "bool"},
                        {"name": "currentReputation", "type": "int256"},
                    ],
                }
            ],
        },
        {
            "type": "function",
            "name": "pendingWithdrawals",
            "stateMutability": "view",
            "inputs": [{"name": "", "type": "address"}],
            "outputs": [
                {"name": "amount", "type": "uint256"},
                {"name": "unlockAt", "type": "uint64"},
            ],
        },
    ]


@stake_app.command("top-up")
def stake_top_up(
    allocator_id: str = typer.Option(..., "--allocator-id", help="Allocator contract address"),
    amount: int = typer.Option(..., help="Amount in USDC base units (6 decimals)."),
    rpc_url: str | None = typer.Option(None, "--rpc-url", help="Defaults to $KITE_RPC_URL."),
    operator_pk: str | None = typer.Option(
        None, "--operator-pk", help="Defaults to $ALLOCATOR_OPERATOR_PK."
    ),
    registry: str | None = typer.Option(
        None, "--registry", help="Defaults to $ALLOCATOR_REGISTRY."
    ),
) -> None:
    """Top up the allocator's stake on `AllocatorRegistry`."""
    if amount <= 0:
        raise typer.BadParameter("amount must be > 0.", param_hint="--amount")
    ctx = _make_stake_context(allocator_id, rpc_url, operator_pk, registry)
    tx_hash = _send_stake_tx(ctx, "topUpStake", [allocator_id, amount])
    console.print(f"[green]top-up submitted[/green] tx={tx_hash} amount={amount}")


@stake_app.command("initiate-withdrawal")
def stake_initiate_withdrawal(
    allocator_id: str = typer.Option(..., "--allocator-id"),
    amount: int = typer.Option(..., help="Amount to schedule for withdrawal."),
    rpc_url: str | None = typer.Option(None, "--rpc-url"),
    operator_pk: str | None = typer.Option(None, "--operator-pk"),
    registry: str | None = typer.Option(None, "--registry"),
) -> None:
    """Start the 7-day stake withdrawal cooldown."""
    if amount <= 0:
        raise typer.BadParameter("amount must be > 0.", param_hint="--amount")
    ctx = _make_stake_context(allocator_id, rpc_url, operator_pk, registry)
    tx_hash = _send_stake_tx(ctx, "initiateStakeWithdrawal", [allocator_id, amount])
    console.print(
        f"[yellow]initiated[/yellow] withdrawal of {amount}; "
        f"completable after the cooldown via `helios-allocator stake withdraw`. tx={tx_hash}"
    )


@stake_app.command("withdraw")
def stake_withdraw(
    allocator_id: str = typer.Option(..., "--allocator-id"),
    rpc_url: str | None = typer.Option(None, "--rpc-url"),
    operator_pk: str | None = typer.Option(None, "--operator-pk"),
    registry: str | None = typer.Option(None, "--registry"),
) -> None:
    """Finalise a previously-initiated withdrawal once cooldown elapses."""
    ctx = _make_stake_context(allocator_id, rpc_url, operator_pk, registry)
    state = _read_stake_state(ctx)
    if state["pendingAmount"] == 0:
        raise typer.BadParameter(
            "no pending withdrawal — call `stake initiate-withdrawal` first.",
            param_hint="--allocator-id",
        )
    if state["unlockAt"] > int(time.time()):
        delta = state["unlockAt"] - int(time.time())
        raise typer.BadParameter(
            f"cooldown active for another {delta}s; cannot finalise yet.",
            param_hint="--allocator-id",
        )
    tx_hash = _send_stake_tx(ctx, "completeStakeWithdrawal", [allocator_id])
    console.print(f"[green]withdrawn[/green] {state['pendingAmount']} units. tx={tx_hash}")


@stake_app.command("balance")
def stake_balance(
    allocator_id: str = typer.Option(..., "--allocator-id"),
    rpc_url: str | None = typer.Option(None, "--rpc-url"),
    operator_pk: str | None = typer.Option(None, "--operator-pk"),
    registry: str | None = typer.Option(None, "--registry"),
) -> None:
    """Print current stake + any pending withdrawal."""
    ctx = _make_stake_context(allocator_id, rpc_url, operator_pk, registry)
    state = _read_stake_state(ctx)
    table = Table(title=f"Stake — {allocator_id}", show_lines=False)
    table.add_column("Field", style="bold")
    table.add_column("Value", justify="right")
    table.add_row("Active", str(state["active"]))
    table.add_row("Stake (base units)", f"{state['stakeAmount']:,}")
    table.add_row("Pending withdrawal", f"{state['pendingAmount']:,}")
    table.add_row("Unlock at (unix)", str(state["unlockAt"]))
    console.print(table)


# ─── deploy ────────────────────────────────────────────────


@app.command()
def deploy(
    project: Path = typer.Option(
        ...,
        help="Path to the scaffolded allocator project (the dir from `init`).",
    ),
    vps: str = typer.Option(..., help="SSH target, e.g. user@host"),
    image_tag: str = typer.Option("helios-allocator:latest", help="Docker image tag."),
) -> None:
    """Build the project's Docker image and run it on a VPS over SSH."""
    project = project.resolve()
    if not (project / "Dockerfile").is_file():
        raise typer.BadParameter(
            f"{project}/Dockerfile missing — is this an allocator scaffold?",
            param_hint="--project",
        )
    console.print(f"[bold]Building[/bold] {image_tag} from {project}")
    _run(
        [
            "docker",
            "build",
            "-t",
            image_tag,
            str(project),
        ]
    )
    console.print(f"[bold]Saving image to tarball and copying to[/bold] {vps}")
    tarball = project / ".dist" / f"{image_tag.replace(':', '_')}.tar"
    tarball.parent.mkdir(parents=True, exist_ok=True)
    _run(["docker", "save", "-o", str(tarball), image_tag])
    _run(["scp", str(tarball), f"{vps}:/tmp/{tarball.name}"])
    remote_cmd = (
        f"docker load -i /tmp/{tarball.name} && "
        f"docker rm -f helios-allocator || true && "
        f"docker run -d --name helios-allocator --restart unless-stopped "
        f"--env-file ~/.helios/allocator.env {image_tag}"
    )
    _run(["ssh", vps, remote_cmd])
    console.print(f"[green]deployed[/green] {image_tag} → {vps}")


def _run(cmd: list[str]) -> None:
    """Wrap subprocess.run so tests can monkeypatch the dispatch."""
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        raise typer.BadParameter(f"command failed (exit {result.returncode}): {' '.join(cmd)}")


# ─── logs ──────────────────────────────────────────────────


@app.command()
def logs(
    vps: str | None = typer.Option(
        None, help="SSH target. If omitted, tails the local docker container."
    ),
    container: str = typer.Option("helios-allocator", help="Container name."),
    lines: int = typer.Option(200, help="Tail this many lines from the end."),
    follow: bool = typer.Option(
        True, "--follow/--no-follow", help="Stream new lines as they arrive."
    ),
) -> None:
    """Stream the structlog JSON log for a running allocator."""
    base = ["docker", "logs", f"--tail={lines}"]
    if follow:
        base.append("-f")
    base.append(container)
    if vps is None:
        _run(base)
    else:
        _run(["ssh", vps, " ".join(base)])


def app_main() -> None:
    app()
