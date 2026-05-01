"""`_loader` — load a StrategyAgent subclass from a Python file."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from helios_cli._loader import StrategyLoadError, instantiate, load_strategy_class


def test_loads_strategy(tiny_strategy_file: Path) -> None:
    cls = load_strategy_class(tiny_strategy_file)
    assert cls.__name__ == "NoopStrategy"
    assert cls.declared_class == "test_class_v1"


def test_instantiate_returns_instance(tiny_strategy_file: Path) -> None:
    agent = instantiate(tiny_strategy_file)
    assert agent.declared_class == "test_class_v1"


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(StrategyLoadError, match="not found"):
        load_strategy_class(tmp_path / "nope.py")


def test_no_subclass(tmp_path: Path) -> None:
    p = tmp_path / "empty.py"
    p.write_text("x = 1\n")
    with pytest.raises(StrategyLoadError, match="no StrategyAgent subclass"):
        load_strategy_class(p)


def test_multiple_subclasses_rejected(tmp_path: Path) -> None:
    p = tmp_path / "two.py"
    p.write_text(
        textwrap.dedent(
            """
            from helios import StrategyAgent

            class A(StrategyAgent):
                declared_class = "a"
                def on_bar(self, asset, snapshot): return None

            class B(StrategyAgent):
                declared_class = "b"
                def on_bar(self, asset, snapshot): return None
            """
        )
    )
    with pytest.raises(StrategyLoadError, match="multiple strategies"):
        load_strategy_class(p)
