"""Load a `StrategyAgent` subclass from a user-supplied Python file.

`helios backtest` / `simulate` / `deploy` all take a `--strategy
./my.py` path. This module imports that file as a one-off module and
returns the first concrete `StrategyAgent` subclass it defines.

Operators ship strategies as a single file or a small package; either
way we only require that the file evaluates and exposes one
`StrategyAgent` subclass."""

from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path

from helios.agent import StrategyAgent


class StrategyLoadError(RuntimeError):
    """Raised when a strategy file does not yield exactly one
    `StrategyAgent` subclass."""


def load_strategy_class(path: Path) -> type[StrategyAgent]:
    """Import `path` as a fresh module; return the contained
    StrategyAgent subclass.

    Multiple subclasses are an error — operators must put their
    strategy in its own file. Inherited subclasses imported from
    `helios.classes.*` (the SDK base classes) are filtered out."""
    if not path.exists():
        raise StrategyLoadError(f"strategy file not found: {path}")

    module_name = f"_helios_user_strategy_{abs(hash(str(path.resolve())))}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise StrategyLoadError(f"could not import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise StrategyLoadError(f"importing {path} failed: {exc}") from exc

    candidates: list[type[StrategyAgent]] = []
    for _, obj in inspect.getmembers(module, inspect.isclass):
        if obj is StrategyAgent:
            continue
        if not issubclass(obj, StrategyAgent):
            continue
        # Only count classes actually defined in the user's module — not
        # the SDK helpers (`helios.classes.MomentumV1Base`, ...) that
        # may be re-exported by `from helios.classes import ...`.
        if obj.__module__ != module_name:
            continue
        candidates.append(obj)

    if not candidates:
        raise StrategyLoadError(
            f"{path} defines no StrategyAgent subclass — "
            "subclass `helios.StrategyAgent` and override `on_bar`."
        )
    if len(candidates) > 1:
        names = ", ".join(c.__name__ for c in candidates)
        raise StrategyLoadError(
            f"{path} defines multiple strategies ({names}); put each in its own file."
        )
    return candidates[0]


def instantiate(path: Path) -> StrategyAgent:
    cls = load_strategy_class(path)
    try:
        return cls()
    except TypeError as exc:
        raise StrategyLoadError(
            f"{cls.__name__} requires constructor args; provide defaults so "
            "`helios backtest` can instantiate it without parameters."
        ) from exc


__all__ = ["StrategyLoadError", "instantiate", "load_strategy_class"]
