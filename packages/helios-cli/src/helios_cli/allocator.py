"""Allocator operator commands.

WS2.A wires the real `init` scaffolder; the rest stay as Phase-0 stubs
until WS2.B fills them in.

`init` walks the bundled template tree at `templates/allocator/`,
substitutes `{{NAME}}` / `{{NAME_PASCAL}}` / `{{NAME_SNAKE}}` /
`{{NAME_KEBAB}}` placeholders, and renames the `__name_snake__`
directory + strips the `.tmpl` suffix from every file. The result is
a runnable Python package that depends on `helios-allocator-sdk` only
(no workspace deps — see `project_strategy_sdk_distribution.md`).
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer(help="Allocator operator commands", no_args_is_help=True)
console = Console()


_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates" / "allocator"

# `Helios *` is reserved for first-party reference brands. The on-chain
# `AllocatorRegistry` constructor pre-seeds the production names; we
# fail fast client-side so operators don't burn a tx on a guaranteed
# revert.
_RESERVED_NAMESPACE = re.compile(r"^helios\b", re.IGNORECASE)


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
    """Walk `src`, render each file/dir into `dst`.

    Directories named `__name_snake__` are renamed to the chosen
    package name. Files ending in `.tmpl` have their suffix stripped
    and contents pass through `str.replace` substitution. Everything
    else copies verbatim.
    """
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
    # Insert underscores before camel-case humps, then split on
    # non-alphanumerics, then lowercase.
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    parts = re.split(r"[^A-Za-z0-9]+", spaced)
    return "_".join(p.lower() for p in parts if p)


def _to_pascal(name: str) -> str:
    """`"test third-party"` → `"TestThirdParty"`."""
    parts = re.split(r"[^A-Za-z0-9]+", name)
    return "".join(p[:1].upper() + p[1:] for p in parts if p)


@app.command()
def backtest(
    allocator: Path = typer.Option(..., help="Path to your BaseAllocator subclass"),
    strategies: str = typer.Option(
        "", help="Comma-separated strategy ids (default: top-50 by reputation)"
    ),
    capital: int = typer.Option(50_000, help="Starting capital in USDC"),
    period: str = typer.Option("90d", help="Backtest period"),
) -> None:
    """Backtest an allocator against historical strategy P&L."""
    console.print(
        f"[yellow]Phase 0 stub.[/yellow] Will backtest {allocator}"
        f" with {capital:,} USDC over {period}."
    )


@app.command()
def simulate(
    allocator: Path = typer.Option(..., help="Path to your BaseAllocator subclass"),
    users: int = typer.Option(100, help="Number of synthetic users"),
) -> None:
    """Run a multi-user simulation against the allocator."""
    console.print(
        f"[yellow]Phase 0 stub.[/yellow] Will simulate {users} users against {allocator}."
    )


@app.command()
def stake(
    action: str = typer.Argument(..., help="top-up | withdraw | initiate-withdrawal"),
    allocator_id: str = typer.Option(..., help="Allocator contract address"),
    amount: int = typer.Option(0, help="Amount in USDC"),
) -> None:
    """Manage allocator stake on the AllocatorRegistry."""
    console.print(
        f"[yellow]Phase 0 stub.[/yellow] Will {action} stake on {allocator_id} ({amount})."
    )


@app.command()
def deploy(
    allocator: Path = typer.Option(..., help="Path to your BaseAllocator subclass"),
    vps: str = typer.Option(..., help="SSH target, e.g. user@host"),
) -> None:
    """Package an allocator as Docker and deploy to a VPS."""
    console.print(f"[yellow]Phase 0 stub.[/yellow] Will deploy {allocator} to {vps}.")


@app.command()
def logs() -> None:
    """Tail live operational events from the running allocator."""
    console.print("[yellow]Phase 0 stub.[/yellow] Will stream operational logs.")


def app_main() -> None:
    app()
