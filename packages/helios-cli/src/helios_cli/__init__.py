"""Helios CLI.

Two entry points:
  - `helios` — strategy operator commands (backtest, deploy, stake, simulate, test-proof)
  - `helios-allocator` — allocator operator commands (init, backtest, simulate, stake, deploy, logs)

Phase 0 ships the command surface as stubs so the CLI is real and callable.
Each phase backfills behavior:
  Phase 2: helios backtest, helios simulate, helios stake top-up
  Phase 3: helios-allocator init, helios-allocator backtest, helios-allocator deploy
"""

import typer

from helios_cli import allocator, strategy

app = typer.Typer(help="Helios — strategy operator CLI", no_args_is_help=True)
app.add_typer(strategy.app, name="strategy", help="Strategy operator commands")


@app.callback(invoke_without_command=False)
def _root() -> None:
    """Helios CLI. Run `helios <command> --help` for details."""


# Re-export typer commands at the top level so `helios backtest` works without `strategy`.
app.command()(strategy.backtest)
app.command()(strategy.simulate)
app.command()(strategy.deploy)
app.command(name="test-proof")(strategy.test_proof)
app.command()(strategy.stake)


def app_main() -> None:
    app()


__all__ = ["allocator", "app", "app_main", "strategy"]
