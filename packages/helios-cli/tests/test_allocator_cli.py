"""Smoke tests for the WS2.B allocator commands.

Each test invokes one subcommand through `typer.testing.CliRunner`,
short-circuiting the heavy-lifting helpers (`_send_stake_tx`,
`_read_stake_state`, `_run`) so the suite stays hermetic and fast.
Live execution is exercised end-to-end in WS7.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from helios_cli import allocator as allocator_cmd
from typer.testing import CliRunner

runner = CliRunner()


# ─── allocator-class loader ────────────────────────────────


_ALLOCATOR_FIXTURE = """
from helios_allocator import BaseAllocator, AllocationTarget, MetaStrategy, StrategyCandidate


class StubAllocator(BaseAllocator):
    name = "Stub"
    fee_rate_bps = 500
    supported_classes = ("momentum_v1", "mean_reversion_v1", "yield_rotation_v1")

    def rank_strategies(self, user, candidates):
        return [c.reputation_score for c in candidates]

    def allocate(self, user, ranked, capital):
        scores = self.rank_strategies(user, ranked)
        return self.score_weighted_allocation(user, ranked, capital, scores=scores)
"""


@pytest.fixture()
def stub_module(tmp_path: Path) -> Path:
    p = tmp_path / "stub_allocator.py"
    p.write_text(_ALLOCATOR_FIXTURE, encoding="utf-8")
    return p


# ─── backtest ──────────────────────────────────────────────


def _nav_fixture(tmp_path: Path, days: int = 35) -> Path:
    rows = [
        {
            "strategy_id": "0xalpha",
            "declared_class": "momentum_v1",
            "fee_rate_bps": 1_500,
            "stake_amount_usd": 10_000,
            "max_capacity_usd": 200_000,
            "reputation_score": 0.85,
            "daily_navs": [100.0 * (1.002**d) for d in range(days)],
        },
        {
            "strategy_id": "0xbeta",
            "declared_class": "mean_reversion_v1",
            "fee_rate_bps": 800,
            "stake_amount_usd": 6_000,
            "max_capacity_usd": 120_000,
            "reputation_score": 0.6,
            "daily_navs": [100.0 * (0.999**d) for d in range(days)],
        },
    ]
    p = tmp_path / "fixture.json"
    p.write_text(json.dumps(rows), encoding="utf-8")
    return p


def test_backtest_runs_against_fixture(tmp_path: Path, stub_module: Path) -> None:
    fixture = _nav_fixture(tmp_path, days=35)
    out = tmp_path / "report.md"
    result = runner.invoke(
        allocator_cmd.app,
        [
            "backtest",
            "--allocator",
            f"{stub_module}:StubAllocator",
            "--period",
            "30d",
            "--capital",
            "10000",
            "--fixture",
            str(fixture),
            "--output",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    assert out.is_file()
    md = out.read_text()
    assert "# Backtest" in md
    assert "Stub" in md


def test_backtest_errors_when_no_fixture_and_no_endpoint(
    tmp_path: Path, stub_module: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GOLDSKY_ENDPOINT", raising=False)
    result = runner.invoke(
        allocator_cmd.app,
        [
            "backtest",
            "--allocator",
            f"{stub_module}:StubAllocator",
            "--period",
            "30d",
        ],
    )
    assert result.exit_code != 0
    # `BadParameter` exits 2 — keep the assertion invariant under
    # typer's pty-width truncation.
    assert result.exit_code == 2


def test_backtest_rejects_bad_allocator_ref(tmp_path: Path) -> None:
    fixture = _nav_fixture(tmp_path)
    result = runner.invoke(
        allocator_cmd.app,
        [
            "backtest",
            "--allocator",
            "not_a_module_ref",
            "--fixture",
            str(fixture),
            "--period",
            "30d",
        ],
    )
    assert result.exit_code == 2


# ─── simulate ──────────────────────────────────────────────


def test_simulate_runs(stub_module: Path) -> None:
    result = runner.invoke(
        allocator_cmd.app,
        [
            "simulate",
            "--allocator",
            f"{stub_module}:StubAllocator",
            "--users",
            "5",
            "--seed",
            "1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "synthetic users" in result.output


def test_simulate_is_deterministic_for_a_seed(stub_module: Path) -> None:
    args = [
        "simulate",
        "--allocator",
        f"{stub_module}:StubAllocator",
        "--users",
        "10",
        "--seed",
        "7",
    ]
    a = runner.invoke(allocator_cmd.app, args)
    b = runner.invoke(allocator_cmd.app, args)
    assert a.exit_code == 0 and b.exit_code == 0
    assert a.output == b.output


# ─── stake ─────────────────────────────────────────────────


_DUMMY_PK = "0x" + "11" * 32
_DUMMY_REGISTRY = "0x" + "22" * 20
_DUMMY_ALLOCATOR_ID = "0x" + "33" * 20


def _stub_send_tx(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, list]]:
    calls: list[tuple[str, list]] = []

    def fake(_ctx, fn_name, args):
        calls.append((fn_name, args))
        return "0xdeadbeef"

    monkeypatch.setattr(allocator_cmd, "_send_stake_tx", fake)
    return calls


def test_stake_top_up_sends_tx(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _stub_send_tx(monkeypatch)
    result = runner.invoke(
        allocator_cmd.app,
        [
            "stake",
            "top-up",
            "--allocator-id",
            _DUMMY_ALLOCATOR_ID,
            "--amount",
            "5000",
            "--rpc-url",
            "http://localhost:8545",
            "--operator-pk",
            _DUMMY_PK,
            "--registry",
            _DUMMY_REGISTRY,
        ],
    )
    assert result.exit_code == 0, result.output
    assert calls == [("topUpStake", [_DUMMY_ALLOCATOR_ID, 5000])]
    assert "top-up submitted" in result.output


def test_stake_top_up_rejects_zero_amount(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_send_tx(monkeypatch)
    result = runner.invoke(
        allocator_cmd.app,
        [
            "stake",
            "top-up",
            "--allocator-id",
            _DUMMY_ALLOCATOR_ID,
            "--amount",
            "0",
            "--rpc-url",
            "http://localhost:8545",
            "--operator-pk",
            _DUMMY_PK,
            "--registry",
            _DUMMY_REGISTRY,
        ],
    )
    assert result.exit_code == 2


def test_stake_initiate_withdrawal_sends_tx(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _stub_send_tx(monkeypatch)
    result = runner.invoke(
        allocator_cmd.app,
        [
            "stake",
            "initiate-withdrawal",
            "--allocator-id",
            _DUMMY_ALLOCATOR_ID,
            "--amount",
            "1000",
            "--rpc-url",
            "http://localhost:8545",
            "--operator-pk",
            _DUMMY_PK,
            "--registry",
            _DUMMY_REGISTRY,
        ],
    )
    assert result.exit_code == 0, result.output
    assert calls == [("initiateStakeWithdrawal", [_DUMMY_ALLOCATOR_ID, 1000])]


def test_stake_withdraw_blocks_when_cooldown_active(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_send_tx(monkeypatch)
    monkeypatch.setattr(
        allocator_cmd,
        "_read_stake_state",
        lambda _ctx: {
            "stakeAmount": 10_000,
            "active": True,
            "pendingAmount": 1_000,
            "unlockAt": 9_999_999_999,  # far future
        },
    )
    result = runner.invoke(
        allocator_cmd.app,
        [
            "stake",
            "withdraw",
            "--allocator-id",
            _DUMMY_ALLOCATOR_ID,
            "--rpc-url",
            "http://localhost:8545",
            "--operator-pk",
            _DUMMY_PK,
            "--registry",
            _DUMMY_REGISTRY,
        ],
    )
    assert result.exit_code == 2  # BadParameter


def test_stake_withdraw_when_cooldown_elapsed(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _stub_send_tx(monkeypatch)
    monkeypatch.setattr(
        allocator_cmd,
        "_read_stake_state",
        lambda _ctx: {
            "stakeAmount": 10_000,
            "active": True,
            "pendingAmount": 1_000,
            "unlockAt": 1,  # in the past
        },
    )
    result = runner.invoke(
        allocator_cmd.app,
        [
            "stake",
            "withdraw",
            "--allocator-id",
            _DUMMY_ALLOCATOR_ID,
            "--rpc-url",
            "http://localhost:8545",
            "--operator-pk",
            _DUMMY_PK,
            "--registry",
            _DUMMY_REGISTRY,
        ],
    )
    assert result.exit_code == 0, result.output
    assert calls == [("completeStakeWithdrawal", [_DUMMY_ALLOCATOR_ID])]


def test_stake_balance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        allocator_cmd,
        "_read_stake_state",
        lambda _ctx: {
            "stakeAmount": 5_000_000_000,
            "active": True,
            "pendingAmount": 0,
            "unlockAt": 0,
        },
    )
    result = runner.invoke(
        allocator_cmd.app,
        [
            "stake",
            "balance",
            "--allocator-id",
            _DUMMY_ALLOCATOR_ID,
            "--rpc-url",
            "http://localhost:8545",
            "--operator-pk",
            _DUMMY_PK,
            "--registry",
            _DUMMY_REGISTRY,
        ],
    )
    assert result.exit_code == 0, result.output
    assert "5,000,000,000" in result.output


def test_stake_missing_env_errors() -> None:
    result = runner.invoke(
        allocator_cmd.app,
        [
            "stake",
            "top-up",
            "--allocator-id",
            _DUMMY_ALLOCATOR_ID,
            "--amount",
            "1",
        ],
    )
    assert result.exit_code == 2  # missing env / flag


# ─── deploy ────────────────────────────────────────────────


def test_deploy_runs_expected_commands(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    project = tmp_path / "alloc"
    project.mkdir()
    (project / "Dockerfile").write_text("FROM python:3.12-slim\n")
    calls: list[list[str]] = []
    monkeypatch.setattr(allocator_cmd, "_run", calls.append)
    result = runner.invoke(
        allocator_cmd.app,
        [
            "deploy",
            "--project",
            str(project),
            "--vps",
            "user@host",
            "--image-tag",
            "myalloc:1",
        ],
    )
    assert result.exit_code == 0, result.output
    # Expected order: build, save, scp, ssh
    assert any(c[:2] == ["docker", "build"] for c in calls)
    assert any(c[:2] == ["docker", "save"] for c in calls)
    assert any(c[0] == "scp" for c in calls)
    assert any(c[0] == "ssh" for c in calls)


def test_deploy_rejects_missing_dockerfile(tmp_path: Path) -> None:
    project = tmp_path / "no-docker"
    project.mkdir()
    result = runner.invoke(
        allocator_cmd.app,
        ["deploy", "--project", str(project), "--vps", "user@host"],
    )
    assert result.exit_code == 2


# ─── logs ──────────────────────────────────────────────────


def test_logs_local_runs_docker_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(allocator_cmd, "_run", calls.append)
    result = runner.invoke(
        allocator_cmd.app,
        ["logs", "--no-follow", "--lines", "50"],
    )
    assert result.exit_code == 0, result.output
    assert calls == [["docker", "logs", "--tail=50", "helios-allocator"]]


def test_logs_remote_runs_ssh(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(allocator_cmd, "_run", calls.append)
    result = runner.invoke(
        allocator_cmd.app,
        ["logs", "--vps", "user@host", "--no-follow", "--lines", "100"],
    )
    assert result.exit_code == 0, result.output
    assert calls and calls[0][0] == "ssh"
    assert calls[0][1] == "user@host"
    assert "docker logs --tail=100 helios-allocator" in calls[0][2]
