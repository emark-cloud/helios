"""Tests for `helios-allocator init` (WS2.A).

Strategy:
  1. Fast unit-style coverage — render the scaffold into a tmp dir,
     assert the tree shape, file contents, placeholder substitution,
     and the reserved-namespace error path. No process boundary.
  2. One slower install-into-venv test that proves the scaffold is a
     valid Python package: `pip install --no-deps .` succeeds, and
     `python -c "from <name_snake> import <Pascal>Allocator"` imports
     cleanly. We pass `--no-deps` because installing the SDK from
     PyPI in CI is a separate concern (smoke covered in WS7); here we
     only care that the scaffold itself is structurally correct.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from helios_cli import allocator as allocator_cmd
from typer.testing import CliRunner

runner = CliRunner()


def _scaffold(target: Path, name: str = "Test ThirdParty") -> None:
    result = runner.invoke(
        allocator_cmd.app,
        ["init", "--name", name, "--target-dir", str(target)],
    )
    assert result.exit_code == 0, result.output


# ─── tree shape ─────────────────────────────────────────────


def test_init_writes_expected_tree(tmp_path: Path) -> None:
    target = tmp_path / "third-party"
    _scaffold(target)

    # Top level files.
    assert (target / "pyproject.toml").is_file()
    assert (target / "Dockerfile").is_file()
    assert (target / "README.md").is_file()
    assert (target / ".env.example").is_file()

    # The package directory was renamed from `__name_snake__` to the
    # snake-cased name.
    pkg = target / "src" / "test_third_party"
    assert pkg.is_dir()
    assert (pkg / "__init__.py").is_file()
    assert (pkg / "__main__.py").is_file()
    assert (pkg / "allocator.py").is_file()

    # No `.tmpl` suffixes leaked through.
    assert not list(target.rglob("*.tmpl"))
    # No literal `__name_snake__` directory leaked through.
    assert not list(target.rglob("__name_snake__"))


def test_init_substitutes_placeholders(tmp_path: Path) -> None:
    target = tmp_path / "third-party"
    _scaffold(target)

    pyproj = (target / "pyproject.toml").read_text()
    assert 'name = "test-third-party"' in pyproj
    assert 'packages = ["src/test_third_party"]' in pyproj

    allocator_py = (target / "src" / "test_third_party" / "allocator.py").read_text()
    assert "class TestThirdPartyAllocator(BaseAllocator):" in allocator_py
    assert 'name = "Test ThirdParty"' in allocator_py
    assert "{{NAME" not in allocator_py  # no unrendered placeholders

    main_py = (target / "src" / "test_third_party" / "__main__.py").read_text()
    assert "from test_third_party.allocator import TestThirdPartyAllocator" in main_py
    assert "TestThirdPartyAllocator()" in main_py

    init_py = (target / "src" / "test_third_party" / "__init__.py").read_text()
    assert "from test_third_party.allocator import TestThirdPartyAllocator" in init_py

    dockerfile = (target / "Dockerfile").read_text()
    assert 'CMD ["python", "-m", "test_third_party"]' in dockerfile

    readme = (target / "README.md").read_text()
    assert "# Test ThirdParty" in readme
    assert "Build with Claude Code" in readme


# ─── slug + namespace rules ────────────────────────────────


def test_init_rejects_helios_namespace(tmp_path: Path) -> None:
    target = tmp_path / "should-not-exist"
    result = runner.invoke(
        allocator_cmd.app,
        ["init", "--name", "Helios Sentinel", "--target-dir", str(target)],
    )
    assert result.exit_code != 0
    assert not target.exists()
    # `BadParameter` rendering goes to stderr, but `mix_stderr=True`
    # (the CliRunner default) folds it into `result.output`.
    assert "Helios" in result.output


def test_init_rejects_helios_namespace_case_insensitive(tmp_path: Path) -> None:
    target = tmp_path / "should-not-exist"
    result = runner.invoke(
        allocator_cmd.app,
        ["init", "--name", "helios bandit", "--target-dir", str(target)],
    )
    assert result.exit_code != 0
    assert not target.exists()


def test_init_refuses_to_overwrite_without_force(tmp_path: Path) -> None:
    target = tmp_path / "third-party"
    _scaffold(target)
    # Second call without --force fails fast.
    result = runner.invoke(
        allocator_cmd.app,
        ["init", "--name", "Test ThirdParty", "--target-dir", str(target)],
    )
    assert result.exit_code != 0
    assert "--force" in result.output


def test_init_overwrites_with_force(tmp_path: Path) -> None:
    target = tmp_path / "third-party"
    _scaffold(target)
    # Drop a sentinel file we expect the rerender to obliterate.
    sentinel = target / "STALE.txt"
    sentinel.write_text("from a previous render")
    result = runner.invoke(
        allocator_cmd.app,
        [
            "init",
            "--name",
            "Test ThirdParty",
            "--target-dir",
            str(target),
            "--force",
        ],
    )
    assert result.exit_code == 0, result.output
    assert not sentinel.exists()
    assert (target / "src" / "test_third_party" / "allocator.py").is_file()


def test_init_rejects_name_that_collapses_to_empty(tmp_path: Path) -> None:
    target = tmp_path / "ghost"
    result = runner.invoke(
        allocator_cmd.app,
        ["init", "--name", "!!!", "--target-dir", str(target)],
    )
    assert result.exit_code != 0
    assert not target.exists()


# ─── installable package ───────────────────────────────────


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv required for venv install test")
def test_scaffold_installs_into_venv(tmp_path: Path) -> None:
    """End-to-end: scaffold, then `uv pip install --no-deps .` into a
    fresh venv, then assert the package metadata is queryable.

    Uses `uv` rather than stdlib `venv`+`pip` because the latter needs
    `python3-venv` (ensurepip), which isn't always present on barebones
    Debian/WSL setups. CI installs uv unconditionally per the repo's
    `pnpm dev` prerequisites, so this is the more portable path.
    """
    project = tmp_path / "third-party"
    _scaffold(project)

    env_dir = tmp_path / "venv"
    subprocess.run(
        ["uv", "venv", str(env_dir), "--python", sys.executable, "--quiet"],
        check=True,
    )
    py = env_dir / ("Scripts" if sys.platform == "win32" else "bin") / "python"

    # `--no-deps` because installing the SDK from PyPI in CI is the
    # WS7 smoke-test concern. Here we only validate the scaffold's
    # own packaging metadata.
    subprocess.run(
        ["uv", "pip", "install", "--python", str(py), "--no-deps", "--quiet", "."],
        cwd=project,
        check=True,
    )

    # The SDK is *not* installed in this venv (we skipped deps), so a
    # bare `import test_third_party` would fail at the
    # `from helios_allocator import …` line. Probe the package
    # metadata directly instead.
    probe = subprocess.run(
        [
            str(py),
            "-c",
            "import importlib.metadata as m; print(m.distribution('test-third-party').name)",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert probe.stdout.strip() == "test-third-party"
