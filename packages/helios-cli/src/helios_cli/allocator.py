"""Allocator operator commands. Phase 0 ships stubs; Phase 3 fills behavior."""

from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer(help="Allocator operator commands", no_args_is_help=True)
console = Console()


@app.command()
def init(
    name: str = typer.Option(
        ..., help='Allocator name. "Helios Sentinel" / "Helios Helix" reserved.'
    ),
    target_dir: Path = typer.Option(Path("./my-allocator"), help="Directory to scaffold into"),
) -> None:
    """Scaffold a new allocator project from the SDK template."""
    console.print(
        f"[yellow]Phase 0 stub.[/yellow] Will scaffold a new allocator named "
        f"[bold]{name}[/bold] at {target_dir}."
    )


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
