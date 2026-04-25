"""Strategy operator commands. Phase 0 ships stubs; phases 1–2 fill behavior."""

from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer(help="Strategy operator commands")
console = Console()


@app.command()
def backtest(
    strategy: Path = typer.Option(..., help="Path to your StrategyAgent subclass"),
    period: str = typer.Option("90d", help="Backtest period: 7d / 30d / 90d / 180d"),
    capital: int = typer.Option(10_000, help="Starting capital in USDC"),
) -> None:
    """Backtest a strategy against historical replay data."""
    console.print(
        f"[yellow]Phase 0 stub.[/yellow] Will backtest [bold]{strategy}[/bold]"
        f" for {period} with ${capital:,}.\n"
        "Implementation lands in Phase 2."
    )


@app.command()
def simulate(
    strategy: Path = typer.Option(..., help="Path to your StrategyAgent subclass"),
    minutes: int = typer.Option(60, help="Simulation length in minutes"),
) -> None:
    """Run a strategy against a mocked-up market for CI."""
    console.print(f"[yellow]Phase 0 stub.[/yellow] Will simulate {strategy} for {minutes} min.")


@app.command()
def deploy(
    strategy: Path = typer.Option(..., help="Path to your StrategyAgent subclass"),
    vps: str = typer.Option(..., help="SSH target, e.g. user@host"),
) -> None:
    """Package a strategy as Docker and deploy to a VPS."""
    console.print(f"[yellow]Phase 0 stub.[/yellow] Will deploy {strategy} to {vps}.")


@app.command()
def test_proof(
    trade_spec: Path = typer.Option(..., help="Path to a trade spec JSON"),
) -> None:
    """Run a full proof generation cycle locally to verify circuit compatibility."""
    console.print(
        f"[yellow]Phase 0 stub.[/yellow] Will generate + verify a proof for {trade_spec}."
    )


@app.command()
def stake(
    action: str = typer.Argument(..., help="top-up | withdraw | initiate-withdrawal"),
    strategy_id: str = typer.Option(..., help="Strategy contract address"),
    amount: int = typer.Option(0, help="Amount in USDC (top-up / initiate-withdrawal only)"),
) -> None:
    """Manage strategy stake on the StrategyRegistry."""
    console.print(
        f"[yellow]Phase 0 stub.[/yellow] Will {action} stake on {strategy_id} ({amount})."
    )
