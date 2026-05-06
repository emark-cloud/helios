"""Strategy operator commands.

WS4.B replaces the Phase 0 stubs with real behavior:

  helios backtest    — run the SDK backtest engine against synthetic
                       prices and write a markdown report under
                       docs/backtests/<class>/<name>_<period>.md.
  helios simulate    — short, deterministic mocked-market loop with
                       per-bar progress (CI-usable; no I/O outside the
                       prints).
  helios deploy      — render Dockerfile + bootstrap script for a VPS
                       deploy. Defaults to dry-run; pass --execute to
                       actually scp + ssh.
  helios stake       — top-up / initiate-withdrawal on the
                       StrategyRegistry (top-up is the WS4.B deliverable;
                       the other actions reuse the same plumbing).
  helios test-proof  — full prover round-trip: POST a witness to the
                       prover service, then read-call the deployed
                       TradeAttestationVerifier with the returned
                       proof + publicSignals.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import typer
from helios.backtest import (
    DEFAULT_FEE_BPS,
    BacktestReport,
    run_backtest,
    synthesize_random_walk,
)
from rich.console import Console

from helios_cli import _deployments
from helios_cli._chain import StakeClient, VerifierReader
from helios_cli._loader import StrategyLoadError, instantiate
from helios_cli._proof import (
    class_to_bytes32,
    proof_to_bytes,
    public_signals_to_uints,
)

app = typer.Typer(help="Strategy operator commands")
console = Console()

# Period → (n_bars, bar_interval_sec). 1-hour bars keep CI-grade backtests
# under a second while still spanning the requested calendar window. The
# operator-guide explains how to override these for finer cadences.
_PERIOD_TABLE: dict[str, tuple[int, int]] = {
    "7d": (7 * 24, 3_600),
    "30d": (30 * 24, 3_600),
    "90d": (90 * 24, 3_600),
    "180d": (180 * 24, 3_600),
}

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_DOCKERFILE_TEMPLATE = _TEMPLATES_DIR / "Dockerfile.strategy"


# ─── helios backtest ──────────────────────────────────────────────


@app.command()
def backtest(
    strategy: Path = typer.Option(..., help="Path to your StrategyAgent subclass"),
    period: str = typer.Option("90d", help="Backtest period: 7d / 30d / 90d / 180d"),
    capital: int = typer.Option(10_000, help="Starting capital in USDC"),
    output_dir: Path = typer.Option(
        Path("docs/backtests"),
        help="Directory under which the report is written.",
    ),
    seed: int = typer.Option(42, help="Synthetic-walk seed (deterministic CI runs)."),
    fee_bps: int = typer.Option(DEFAULT_FEE_BPS, help="Round-trip fee per fill."),
) -> None:
    """Backtest a strategy against synthetic prices.

    Writes a markdown report keyed by `<declared_class>/<filename>_<period>.md`
    so a `docs/backtests/<class>/` folder accrues one file per published
    strategy — exactly the layout the operator-guide and the per-class
    reputation cohort docs link to."""
    if period not in _PERIOD_TABLE:
        raise typer.BadParameter(
            f"period must be one of {sorted(_PERIOD_TABLE)}", param_hint="--period"
        )
    bars, bar_interval = _PERIOD_TABLE[period]
    agent = _load(strategy)

    assets = list(agent.asset_universe) or ["BTC", "ETH", "SOL"]
    prices = synthesize_random_walk(assets=assets, bars=bars, seed=seed)
    report = run_backtest(
        strategy=agent,
        prices=prices,
        initial_capital=float(capital),
        bar_interval_sec=bar_interval,
        fee_bps=fee_bps,
    )

    declared_class = agent.declared_class or "uncategorized"
    out_dir = output_dir / declared_class
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{strategy.stem}_{period}.md"
    out_file.write_text(_render_report(agent, report, period, seed))
    console.print(report.summary())
    console.print(f"[green]Report:[/green] {out_file}")


def _render_report(agent: Any, report: BacktestReport, period: str, seed: int) -> str:
    return (
        f"# Backtest — {type(agent).__name__} ({agent.declared_class})\n\n"
        f"- **Period:** {period} (synthetic random walk, seed={seed})\n"
        f"- **Asset universe:** {', '.join(agent.asset_universe) or '—'}\n"
        f"- **Bars simulated:** {report.bars}\n"
        f"- **Initial capital:** ${report.initial_capital:,.2f}\n"
        f"- **Final NAV:** ${report.final_nav:,.2f}\n"
        f"- **Total return:** {report.total_return * 100:+.2f}%\n"
        f"- **Sharpe (annualised):** {report.sharpe:.2f}\n"
        f"- **Max drawdown:** {report.max_drawdown * 100:.2f}%\n"
        f"- **Realized P&L:** ${report.realized_pnl:+,.2f}\n"
        f"- **Trades:** {len(report.fills)}\n"
        f"- **Win rate:** {report.win_rate * 100:.1f}%\n\n"
        "## NAV path\n\n"
        "```\n" + _ascii_nav(report.nav_series) + "\n```\n"
    )


def _ascii_nav(navs: list[float], width: int = 60, height: int = 10) -> str:
    if not navs:
        return "(no data)"
    if len(navs) > width:
        step = len(navs) / width
        sample = [navs[int(i * step)] for i in range(width)]
    else:
        sample = list(navs)
    lo, hi = min(sample), max(sample)
    if hi == lo:
        return "─" * len(sample)
    rows: list[str] = []
    for r in range(height, 0, -1):
        threshold = lo + (hi - lo) * (r / height)
        rows.append("".join("█" if v >= threshold else " " for v in sample))
    rows.append("─" * len(sample))
    return "\n".join(rows)


# ─── helios simulate ──────────────────────────────────────────────


@app.command()
def simulate(
    strategy: Path = typer.Option(..., help="Path to your StrategyAgent subclass"),
    minutes: int = typer.Option(60, help="Simulation length in minutes"),
    seed: int = typer.Option(7, help="Synthetic-walk seed."),
) -> None:
    """Run a strategy against a 1-minute mocked-up market.

    Deterministic; finishes in <1 sec for typical horizons. Prints a
    one-line status every 10 bars so CI logs are scannable."""
    agent = _load(strategy)
    assets = list(agent.asset_universe) or ["BTC", "ETH", "SOL"]
    if minutes < 2:
        raise typer.BadParameter("minutes must be ≥ 2", param_hint="--minutes")
    prices = synthesize_random_walk(assets=assets, bars=minutes, seed=seed)
    report = run_backtest(
        strategy=agent,
        prices=prices,
        initial_capital=10_000.0,
        bar_interval_sec=60,
    )

    fills_by_bar: dict[int, int] = {}
    for f in report.fills:
        fills_by_bar[f.bar] = fills_by_bar.get(f.bar, 0) + 1
    for bar in range(0, minutes, 10):
        cum_fills = sum(c for b, c in fills_by_bar.items() if b <= bar)
        nav = report.nav_series[min(bar, len(report.nav_series) - 1)]
        console.print(f"[dim]bar {bar:>4}[/dim]  nav=${nav:>10,.2f}  fills={cum_fills}")
    console.print(report.summary())


# ─── helios deploy ────────────────────────────────────────────────


@app.command()
def deploy(
    strategy: Path = typer.Option(..., help="Path to your StrategyAgent subclass"),
    vps: str = typer.Option(..., help="SSH target, e.g. user@host"),
    remote_dir: str = typer.Option(
        "/opt/helios-strategy", help="Remote workdir (created if missing)."
    ),
    image_tag: str = typer.Option("helios-strategy:latest", help="Docker image tag."),
    container_name: str = typer.Option("helios-strategy", help="Docker container name."),
    requirements: Path | None = typer.Option(
        None, help="Optional requirements.txt to add into the image."
    ),
    execute: bool = typer.Option(
        False, "--execute", help="Actually run scp/ssh. Defaults to dry-run."
    ),
) -> None:
    """Package a strategy as Docker and bootstrap it on a VPS.

    Generates a Dockerfile from `templates/Dockerfile.strategy` and a
    bootstrap script that scp's the build context, then ssh-runs
    `docker build` + `docker run`. Defaults to dry-run so the operator
    can review the plan before any bytes leave the workstation."""
    if not strategy.exists():
        raise typer.BadParameter(f"strategy file not found: {strategy}")
    _validate_ssh_target(vps)
    _ = _load(strategy)  # validates the file before any network I/O
    if not _DOCKERFILE_TEMPLATE.exists():
        raise typer.BadParameter(
            f"Dockerfile template missing at {_DOCKERFILE_TEMPLATE}; reinstall helios-cli."
        )

    dockerfile = _DOCKERFILE_TEMPLATE.read_text()
    extra_reqs = requirements.read_text() if requirements and requirements.exists() else ""

    # PR4: prior versions printed an `ssh/scp` plan that didn't match
    # `_execute_deploy`'s actual behavior (the real path uses `ssh -- target
    # 'cat > path'` for file transfer; the preview showed `scp <(printf …)`
    # which is bash-only and wouldn't work for everyone). Print a concise
    # description that mirrors what `_execute_deploy` will do.
    console.print("[bold]Deploy plan:[/bold]")
    console.print(f"  target          : {vps}:{remote_dir}")
    console.print("  uploads         : strategy.py, Dockerfile, requirements.extra.txt")
    console.print(f"  build           : docker build -t {image_tag} .")
    console.print(
        f"  run (--rm prior): docker run -d --restart unless-stopped --name {container_name}"
    )

    if not execute:
        console.print(
            "\n[yellow]Dry-run.[/yellow] Re-run with --execute to apply, or copy the "
            "commands above and run them manually."
        )
        return

    _execute_deploy(
        vps=vps,
        remote_dir=remote_dir,
        strategy=strategy,
        dockerfile=dockerfile,
        extra_reqs=extra_reqs,
        image_tag=image_tag,
        container_name=container_name,
    )
    console.print(f"[green]Deployed[/green] {strategy.name} to {vps}:{remote_dir}.")


def _execute_deploy(
    *,
    vps: str,
    remote_dir: str,
    strategy: Path,
    dockerfile: str,
    extra_reqs: str,
    image_tag: str,
    container_name: str,
) -> None:
    _ssh(vps, f"mkdir -p {shlex.quote(remote_dir)}")
    _scp(strategy.read_bytes(), vps, f"{remote_dir}/strategy.py")
    _scp(dockerfile.encode(), vps, f"{remote_dir}/Dockerfile")
    _scp(extra_reqs.encode(), vps, f"{remote_dir}/requirements.extra.txt")
    _ssh(
        vps,
        " && ".join(
            [
                f"cd {shlex.quote(remote_dir)}",
                f"docker build -t {shlex.quote(image_tag)} .",
                f"docker rm -f {shlex.quote(container_name)} 2>/dev/null || true",
                f"docker run -d --restart unless-stopped "
                f"--name {shlex.quote(container_name)} {shlex.quote(image_tag)}",
            ]
        ),
    )


def _validate_ssh_target(target: str) -> None:
    """Reject targets that begin with `-`, which OpenSSH would parse as
    a flag (`-oProxyCommand=...`). `--` after `ssh` makes the option
    parser stop, but we also fail-fast with a clearer error."""
    if target.startswith("-"):
        raise typer.BadParameter(
            f"--vps target {target!r} starts with '-'; refusing to invoke ssh "
            "(would be parsed as an OpenSSH flag, not a hostname)."
        )


def _ssh(target: str, cmd: str) -> None:
    _validate_ssh_target(target)
    # `--` separates options from positional args; combined with the
    # leading-dash check above, this neutralizes option-injection via
    # the user-supplied `--vps` value.
    subprocess.run(["ssh", "--", target, cmd], check=True)


def _scp(payload: bytes, target: str, remote_path: str) -> None:
    _validate_ssh_target(target)
    proc = subprocess.run(
        ["ssh", "--", target, f"cat > {shlex.quote(remote_path)}"],
        input=payload,
        check=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"scp to {target}:{remote_path} failed")


# ─── helios stake ─────────────────────────────────────────────────


@app.command()
def stake(
    action: str = typer.Argument(..., help="top-up | initiate-withdrawal | claim-withdrawal"),
    strategy_id: str = typer.Option(..., help="Strategy contract address"),
    amount: int = typer.Option(0, help="Amount in USDC base units (top-up / withdrawal)"),
    chain: str = typer.Option(
        _deployments.DEFAULT_CHAIN, help="Deployment chain key (default kite-testnet)."
    ),
    rpc_url: str | None = typer.Option(
        None, envvar="KITE_RPC_URL", help="RPC endpoint (env: KITE_RPC_URL)."
    ),
    operator_pk: str | None = typer.Option(
        None,
        envvar="OPERATOR_PK",
        help="Operator signing key (env: OPERATOR_PK).",
    ),
    registry: str | None = typer.Option(
        None, help="Override StrategyRegistry address (default: deployments file)."
    ),
    usdc: str | None = typer.Option(
        None, help="Override USDC token address (default: deployments file)."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print the planned tx without submitting."
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip the interactive confirmation prompt (use in CI / scripts).",
    ),
) -> None:
    """Manage strategy stake on the StrategyRegistry.

    `top-up` is the WS4.B deliverable: approve USDC then call
    `topUpStake(strategyId, amount)`. `initiate-withdrawal` and
    `claim-withdrawal` reuse the same plumbing so the CLI is symmetric
    with the on-chain stake state machine."""
    actions = {"top-up", "initiate-withdrawal", "claim-withdrawal"}
    if action not in actions:
        raise typer.BadParameter(f"action must be one of {sorted(actions)}")
    if action in {"top-up", "initiate-withdrawal"} and amount <= 0:
        raise typer.BadParameter(f"--amount must be > 0 for {action}")

    deployment = _deployments.load(chain)
    registry_addr = registry or deployment.require("strategyRegistry")
    usdc_addr = usdc or deployment.require("usdc")

    plan = {
        "action": action,
        "chain": chain,
        "chainId": deployment.chain_id,
        "registry": registry_addr,
        "usdc": usdc_addr,
        "strategyId": strategy_id,
        "amount": amount,
    }
    console.print("[bold]Plan:[/bold]")
    console.print(json.dumps(plan, indent=2))

    if dry_run:
        console.print("[yellow]Dry-run — no tx submitted.[/yellow]")
        return
    if not rpc_url or not operator_pk:
        raise typer.BadParameter(
            "live mode requires --rpc-url + --operator-pk (or KITE_RPC_URL + OPERATOR_PK)"
        )
    # Confirm before broadcasting. A typo in --strategy-id or --amount is
    # an irrevocable on-chain tx with operator-key authority; opt-in for
    # the kind of automation that doesn't have a TTY (CI, scripts).
    if not yes:
        typer.confirm(
            f"Submit {action} on-chain to {registry_addr} on {chain}?",
            abort=True,
        )

    client = StakeClient(
        rpc_url=rpc_url,
        operator_pk=operator_pk,
        chain_id=deployment.chain_id,
        registry=registry_addr,
        usdc=usdc_addr,
    )
    if action == "top-up":
        approve_hash = client.approve(amount)
        console.print(f"[green]approve[/green] tx={approve_hash}")
        topup_hash = client.top_up(strategy_id, amount)
        console.print(f"[green]topUpStake[/green] tx={topup_hash}")
    elif action == "initiate-withdrawal":
        tx = client.initiate_withdrawal(strategy_id, amount)
        console.print(f"[green]initiateStakeWithdrawal[/green] tx={tx}")
    else:
        tx = client.claim_withdrawal(strategy_id)
        console.print(f"[green]claimStakeWithdrawal[/green] tx={tx}")


# ─── helios test-proof ────────────────────────────────────────────


@app.command(name="test-proof")
def test_proof(
    trade_spec: Path = typer.Option(..., "--trade", help="Path to a trade spec JSON"),
    prover_url: str = typer.Option(
        "http://localhost:8004",
        envvar="PROVER_URL",
        help="Prover service base URL (env: PROVER_URL).",
    ),
    chain: str = typer.Option(
        _deployments.DEFAULT_CHAIN, help="Deployment chain key (default kite-testnet)."
    ),
    rpc_url: str | None = typer.Option(
        None, envvar="KITE_RPC_URL", help="RPC endpoint for the verifier read-call."
    ),
    verifier: str | None = typer.Option(
        None,
        help="Override TradeAttestationVerifier address (default: deployments file).",
    ),
    skip_onchain: bool = typer.Option(
        False, "--skip-onchain", help="Skip the verifier read-call (CI/no-RPC mode)."
    ),
) -> None:
    """Full proof cycle: build witness → POST prover → verifier read-call.

    The trade spec is a JSON file shaped like:

        {
          "strategyClass": "momentum_v1",
          "witnessInputs": { ...inputs the circuit expects... },
          "declaredClass": "momentum_v1"  // optional override
        }

    The CLI POSTs to `<prover_url>/prove`, packs the returned snarkjs
    proof into the 256-byte form the verifier accepts, then read-calls
    `TradeAttestationVerifier.verify(declaredClass, proof, publicInputs)`.
    Exits non-zero if the verifier returns false."""
    spec = json.loads(trade_spec.read_text())
    strategy_class = spec.get("strategyClass") or spec.get("strategy_class")
    witness_inputs = spec.get("witnessInputs") or spec.get("witness_inputs")
    if not strategy_class or witness_inputs is None:
        raise typer.BadParameter("trade spec must include `strategyClass` and `witnessInputs`.")
    declared_class = spec.get("declaredClass") or spec.get("declared_class") or strategy_class

    started = time.time()
    console.print(f"[dim]POST {prover_url}/prove[/dim] (class={strategy_class})")
    try:
        resp = httpx.post(
            f"{prover_url.rstrip('/')}/prove",
            json={"strategyClass": strategy_class, "witnessInputs": witness_inputs},
            timeout=40.0,
        )
    except httpx.HTTPError as exc:
        console.print(f"[red]prover unreachable:[/red] {exc}")
        raise typer.Exit(code=2) from exc
    if resp.status_code != 200:
        console.print(f"[red]prover {resp.status_code}:[/red] {resp.text}")
        raise typer.Exit(code=2)
    body = resp.json()
    proof = body["proof"]
    public_signals = [str(s) for s in body.get("publicSignals") or []]
    console.print(
        f"[green]proof ok[/green] in {(time.time() - started) * 1000:.0f} ms "
        f"({len(public_signals)} public signals)"
    )

    if skip_onchain:
        console.print("[yellow]--skip-onchain set; not calling verifier.[/yellow]")
        return

    deployment = _deployments.load(chain)
    verifier_addr = verifier or deployment.require("tradeAttestationVerifier")
    rpc = rpc_url or os.environ.get("KITE_RPC_URL")
    if not rpc:
        raise typer.BadParameter(
            "verifier read-call requires --rpc-url or KITE_RPC_URL (or pass --skip-onchain)."
        )

    reader = VerifierReader(rpc_url=rpc, verifier_address=verifier_addr)
    ok = reader.verify(
        class_to_bytes32(declared_class),
        proof_to_bytes(proof),
        public_signals_to_uints(public_signals),
    )
    if ok:
        console.print(f"[green]verifier accepted[/green] (verifier={verifier_addr})")
    else:
        console.print(f"[red]verifier REJECTED[/red] (verifier={verifier_addr})")
        raise typer.Exit(code=1)


# ─── helios scaffold-strategy ─────────────────────────────────────


_STRATEGY_TEMPLATES_DIR = _TEMPLATES_DIR / "strategy"
_KNOWN_CLASSES = ("momentum_v1", "mean_reversion_v1", "yield_rotation_v1")


@app.command(name="scaffold-strategy")
def scaffold_strategy(
    strategy_class: str = typer.Argument(
        ...,
        metavar="CLASS",
        help=f"Strategy class. One of: {', '.join(_KNOWN_CLASSES)}",
    ),
    name: str = typer.Option(
        ...,
        help="Strategy name. Becomes the package name and the on-chain manifest name.",
    ),
    target_dir: Path = typer.Option(
        Path("./my-strategy"),
        help="Directory to scaffold into. Created if missing.",
    ),
    force: bool = typer.Option(
        False, "--force", help="Overwrite the target directory if it already exists."
    ),
) -> None:
    """Scaffold a new strategy project from the SDK template.

    Mirrors `helios-allocator init`: a single `pip install -e .` away from
    a runnable backtest, and a `helios deploy` away from a live VPS
    deployment. The SDK is the only runtime dependency — there are no
    workspace imports, so the scaffold installs from public PyPI.
    """
    if strategy_class not in _KNOWN_CLASSES:
        raise typer.BadParameter(
            f"unknown class {strategy_class!r}; pick one of {list(_KNOWN_CLASSES)}.",
            param_hint="CLASS",
        )

    name = name.strip()
    if not name:
        raise typer.BadParameter("--name must be a non-empty string.", param_hint="--name")

    name_snake = _to_snake(name)
    name_pascal = _to_pascal(name)
    name_kebab = name_snake.replace("_", "-")
    if not name_snake or not name_snake.isidentifier():
        raise typer.BadParameter(
            f"--name {name!r} produces snake_case {name_snake!r} which is not a "
            "valid Python identifier. Use ASCII letters, digits, and spaces.",
            param_hint="--name",
        )

    src = _STRATEGY_TEMPLATES_DIR / strategy_class
    if not src.exists():
        raise typer.BadParameter(
            f"template missing at {src}; reinstall helios-cli.",
        )

    target = target_dir.resolve()
    if target.exists():
        if not force:
            raise typer.BadParameter(
                f"target {target} already exists; pass --force to overwrite.",
                param_hint="--target-dir",
            )
        shutil.rmtree(target)

    substitutions = {
        "{{NAME}}": name,
        "{{NAME_PASCAL}}": name_pascal,
        "{{NAME_SNAKE}}": name_snake,
        "{{NAME_KEBAB}}": name_kebab,
    }
    _render_template_tree(src, target, substitutions, name_snake)

    console.print(f"[green]Scaffolded[/green] [bold]{name}[/bold] ({strategy_class}) at {target}")
    console.print(
        f"Next: `pip install -e {target}` then "
        f"`helios backtest --strategy {target}/src/{name_snake}/strategy.py --period 90d`."
    )


def _render_template_tree(
    src: Path,
    dst: Path,
    substitutions: dict[str, str],
    name_snake: str,
) -> None:
    """Walk `src`, render each file/dir into `dst`. Mirrors the
    allocator scaffold renderer but kept local so the strategy and
    allocator commands don't reach into each other's modules."""
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
    """`"My Momentum"` → `"my_momentum"`."""
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    parts = re.split(r"[^A-Za-z0-9]+", spaced)
    return "_".join(p.lower() for p in parts if p)


def _to_pascal(name: str) -> str:
    """`"my momentum-v1"` → `"MyMomentumV1"`."""
    parts = re.split(r"[^A-Za-z0-9]+", name)
    return "".join(p[:1].upper() + p[1:] for p in parts if p)


# ─── shared ───────────────────────────────────────────────────────


def _load(strategy: Path) -> Any:
    try:
        return instantiate(strategy)
    except StrategyLoadError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc


__all__ = [
    "app",
    "backtest",
    "deploy",
    "scaffold_strategy",
    "simulate",
    "stake",
    "test_proof",
]


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())
