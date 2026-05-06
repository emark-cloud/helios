"""Tests for `helios scaffold-strategy <class>` (WS2.C).

Mirrors `test_allocator_init.py` strategy:
  1. Per-class fast unit-style coverage — render the scaffold into a
     tmp dir, assert tree shape, file contents, placeholder
     substitution, and the unknown-class / overwrite error paths.
  2. One slower install-into-venv test that proves the rendered tree
     is a valid Python package (`uv pip install --no-deps`).

The `--no-deps` install matches the allocator-init test: we validate
the scaffold's own packaging metadata. PyPI-install of the SDK is the
WS7 e2e concern.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from helios_cli import strategy as strategy_cmd
from typer.testing import CliRunner

runner = CliRunner()

_CLASSES = ("momentum_v1", "mean_reversion_v1", "yield_rotation_v1")


def _scaffold(target: Path, *, klass: str = "momentum_v1", name: str = "My Mom") -> None:
    result = runner.invoke(
        strategy_cmd.app,
        ["scaffold-strategy", klass, "--name", name, "--target-dir", str(target)],
    )
    assert result.exit_code == 0, result.output


# ─── tree shape (per class) ────────────────────────────────


@pytest.mark.parametrize("klass", _CLASSES)
def test_scaffold_writes_expected_tree(tmp_path: Path, klass: str) -> None:
    target = tmp_path / "my-strat"
    _scaffold(target, klass=klass, name="My Strat")

    # Top level files.
    assert (target / "pyproject.toml").is_file()
    assert (target / "Dockerfile").is_file()
    assert (target / "README.md").is_file()
    assert (target / ".env.example").is_file()

    # The package directory was renamed from `__name_snake__` to the
    # snake-cased name.
    pkg = target / "src" / "my_strat"
    assert pkg.is_dir()
    assert (pkg / "__init__.py").is_file()
    assert (pkg / "strategy.py").is_file()

    # No `.tmpl` suffixes leaked through.
    assert not list(target.rglob("*.tmpl"))
    # No literal `__name_snake__` directory leaked through.
    assert not list(target.rglob("__name_snake__"))


# ─── placeholder substitution (per class) ──────────────────


@pytest.mark.parametrize("klass", _CLASSES)
def test_scaffold_substitutes_placeholders(tmp_path: Path, klass: str) -> None:
    target = tmp_path / "my-strat"
    _scaffold(target, klass=klass, name="My Strat")

    pyproj = (target / "pyproject.toml").read_text()
    assert 'name = "my-strat"' in pyproj
    assert 'packages = ["src/my_strat"]' in pyproj
    assert klass in pyproj  # description carries the class name

    strategy_py = (target / "src" / "my_strat" / "strategy.py").read_text()
    assert f'declared_class = "{klass}"' in strategy_py
    assert "class MyStratStrategy(StrategyAgent):" in strategy_py
    assert "{{NAME" not in strategy_py  # no unrendered placeholders

    init_py = (target / "src" / "my_strat" / "__init__.py").read_text()
    assert "from my_strat.strategy import MyStratStrategy" in init_py

    dockerfile = (target / "Dockerfile").read_text()
    assert 'CMD ["python", "-m", "my_strat"]' in dockerfile

    readme = (target / "README.md").read_text()
    assert "# My Strat" in readme
    assert "Build with Claude Code" in readme


# ─── error paths ───────────────────────────────────────────


def test_scaffold_rejects_unknown_class(tmp_path: Path) -> None:
    target = tmp_path / "ghost"
    result = runner.invoke(
        strategy_cmd.app,
        [
            "scaffold-strategy",
            "imaginary_v9",
            "--name",
            "Bad",
            "--target-dir",
            str(target),
        ],
    )
    assert result.exit_code != 0
    assert not target.exists()


def test_scaffold_rejects_empty_name(tmp_path: Path) -> None:
    target = tmp_path / "ghost"
    result = runner.invoke(
        strategy_cmd.app,
        [
            "scaffold-strategy",
            "momentum_v1",
            "--name",
            "   ",
            "--target-dir",
            str(target),
        ],
    )
    assert result.exit_code != 0
    assert not target.exists()


def test_scaffold_rejects_name_that_collapses_to_empty(tmp_path: Path) -> None:
    target = tmp_path / "ghost"
    result = runner.invoke(
        strategy_cmd.app,
        [
            "scaffold-strategy",
            "momentum_v1",
            "--name",
            "!!!",
            "--target-dir",
            str(target),
        ],
    )
    assert result.exit_code != 0
    assert not target.exists()


def test_scaffold_refuses_to_overwrite_without_force(tmp_path: Path) -> None:
    target = tmp_path / "my-strat"
    _scaffold(target)
    sentinel = target / "STALE.txt"
    sentinel.write_text("from a previous render")
    result = runner.invoke(
        strategy_cmd.app,
        [
            "scaffold-strategy",
            "momentum_v1",
            "--name",
            "My Mom",
            "--target-dir",
            str(target),
        ],
    )
    # `BadParameter` exits 2; we don't sniff the rendered panel because
    # typer's terminal renderer truncates the message to fit the
    # detected width (CI's narrow pty drops the `--force` substring).
    assert result.exit_code == 2
    assert sentinel.exists()


def test_scaffold_overwrites_with_force(tmp_path: Path) -> None:
    target = tmp_path / "my-strat"
    _scaffold(target)
    sentinel = target / "STALE.txt"
    sentinel.write_text("from a previous render")
    result = runner.invoke(
        strategy_cmd.app,
        [
            "scaffold-strategy",
            "momentum_v1",
            "--name",
            "My Mom",
            "--target-dir",
            str(target),
            "--force",
        ],
    )
    assert result.exit_code == 0, result.output
    assert not sentinel.exists()
    assert (target / "src" / "my_mom" / "strategy.py").is_file()


# ─── installable package ───────────────────────────────────


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv required for venv install test")
def test_scaffold_installs_into_venv(tmp_path: Path) -> None:
    """End-to-end: scaffold a momentum_v1 strategy, then
    `uv pip install --no-deps .` into a fresh venv, then assert the
    package metadata is queryable.

    `--no-deps` because installing the SDK from PyPI in CI is the WS7
    smoke-test concern. Here we only validate the scaffold's own
    packaging metadata — the same posture as `test_allocator_init.py`."""
    project = tmp_path / "my-strat"
    _scaffold(project, klass="momentum_v1", name="My Strat")

    env_dir = tmp_path / "venv"
    subprocess.run(
        ["uv", "venv", str(env_dir), "--python", sys.executable, "--quiet"],
        check=True,
    )
    py = env_dir / ("Scripts" if sys.platform == "win32" else "bin") / "python"

    subprocess.run(
        ["uv", "pip", "install", "--python", str(py), "--no-deps", "--quiet", "."],
        cwd=project,
        check=True,
    )

    probe = subprocess.run(
        [
            str(py),
            "-c",
            "import importlib.metadata as m; print(m.distribution('my-strat').name)",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert probe.stdout.strip() == "my-strat"
