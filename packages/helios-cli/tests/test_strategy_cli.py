"""End-to-end CLI tests using `typer.testing.CliRunner`.

The runner invokes the same Typer app the `helios` script wraps, so
`exit_code == 0` proves the command's plumbing — argument parsing,
strategy load, backtest engine, output writing — works as a unit.
Live-mode chain calls are exercised separately via the `_chain`
module's monkeypatched fixtures (no live RPC required)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from helios_cli import strategy as strategy_cmd
from typer.testing import CliRunner

runner = CliRunner()


# ── helios backtest ────────────────────────────────────────────────


def test_backtest_writes_report(tiny_strategy_file: Path, tmp_path: Path) -> None:
    out_dir = tmp_path / "reports"
    result = runner.invoke(
        strategy_cmd.app,
        [
            "backtest",
            "--strategy",
            str(tiny_strategy_file),
            "--period",
            "7d",
            "--output-dir",
            str(out_dir),
        ],
    )
    assert result.exit_code == 0, result.output
    expected = out_dir / "test_class_v1" / "noop_7d.md"
    assert expected.exists()
    body = expected.read_text()
    assert "Backtest" in body
    assert "test_class_v1" in body


def test_backtest_rejects_bad_period(tiny_strategy_file: Path) -> None:
    result = runner.invoke(
        strategy_cmd.app,
        ["backtest", "--strategy", str(tiny_strategy_file), "--period", "1y"],
    )
    assert result.exit_code != 0
    assert "period" in result.output


def test_backtest_missing_strategy_file(tmp_path: Path) -> None:
    result = runner.invoke(
        strategy_cmd.app,
        ["backtest", "--strategy", str(tmp_path / "missing.py")],
    )
    assert result.exit_code != 0


# ── helios simulate ────────────────────────────────────────────────


def test_simulate_runs(tiny_strategy_file: Path) -> None:
    result = runner.invoke(
        strategy_cmd.app,
        ["simulate", "--strategy", str(tiny_strategy_file), "--minutes", "20"],
    )
    assert result.exit_code == 0, result.output
    assert "bar" in result.output


def test_simulate_rejects_short_horizon(tiny_strategy_file: Path) -> None:
    result = runner.invoke(
        strategy_cmd.app,
        ["simulate", "--strategy", str(tiny_strategy_file), "--minutes", "1"],
    )
    assert result.exit_code != 0


# ── helios deploy ──────────────────────────────────────────────────


def test_deploy_dry_run_prints_plan(tiny_strategy_file: Path) -> None:
    result = runner.invoke(
        strategy_cmd.app,
        ["deploy", "--strategy", str(tiny_strategy_file), "--vps", "user@host"],
    )
    assert result.exit_code == 0, result.output
    assert "Dry-run" in result.output
    # PR4: plan now mirrors `_execute_deploy` rather than misleading
    # `scp <(printf …)` shell strings — assert on the new descriptive
    # shape (target host:port, build step) instead.
    assert "user@host:/opt/helios-strategy" in result.output
    assert "docker build" in result.output


def test_deploy_rejects_dash_prefixed_vps(tiny_strategy_file: Path) -> None:
    """`--vps -oProxyCommand=...` would be parsed as an OpenSSH option,
    yielding arbitrary command execution. Fail closed."""
    result = runner.invoke(
        strategy_cmd.app,
        [
            "deploy",
            "--strategy",
            str(tiny_strategy_file),
            "--vps",
            "-oProxyCommand=/tmp/x",
        ],
    )
    assert result.exit_code != 0
    # Click renders BadParameter through Rich; assert we never reached the
    # "Dry-run" branch nor printed the docker plan.
    assert "Dry-run" not in result.output
    assert "docker build" not in result.output


# ── helios stake ───────────────────────────────────────────────────


def test_stake_topup_dry_run(deployments_dir: Path) -> None:
    result = runner.invoke(
        strategy_cmd.app,
        [
            "stake",
            "top-up",
            "--strategy-id",
            "0x" + "11" * 20,
            "--amount",
            "1000",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Dry-run" in result.output
    plan = json.loads(result.output.split("Plan:")[1].split("Dry-run")[0])
    assert plan["action"] == "top-up"
    assert plan["amount"] == 1000
    assert plan["chainId"] == 2368


def test_stake_rejects_unknown_action(deployments_dir: Path) -> None:
    result = runner.invoke(
        strategy_cmd.app,
        ["stake", "rug-pull", "--strategy-id", "0x" + "11" * 20, "--amount", "1"],
    )
    assert result.exit_code != 0


def test_stake_topup_requires_amount(deployments_dir: Path) -> None:
    result = runner.invoke(
        strategy_cmd.app,
        ["stake", "top-up", "--strategy-id", "0x" + "11" * 20, "--amount", "0"],
    )
    assert result.exit_code != 0


def test_stake_live_aborts_without_confirmation(
    deployments_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Live mode must confirm before broadcasting. Sending a 'no' answer
    must abort the run cleanly without ever instantiating `StakeClient`."""
    monkeypatch.setenv("KITE_RPC_URL", "http://stub")
    monkeypatch.setenv("OPERATOR_PK", "0x" + "11" * 32)
    # Fail loudly if confirmation is bypassed and we reach the client.
    monkeypatch.setattr(
        strategy_cmd,
        "StakeClient",
        lambda **_: pytest.fail("StakeClient must not be constructed without confirmation"),
    )
    result = runner.invoke(
        strategy_cmd.app,
        [
            "stake",
            "top-up",
            "--strategy-id",
            "0x" + "11" * 20,
            "--amount",
            "100",
        ],
        input="n\n",
    )
    assert result.exit_code != 0
    assert "Aborted" in result.output or result.exit_code == 1


def test_stake_live_yes_skips_confirmation(
    deployments_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--yes` must bypass the confirm prompt for CI / scripted usage."""
    monkeypatch.setenv("KITE_RPC_URL", "http://stub")
    monkeypatch.setenv("OPERATOR_PK", "0x" + "11" * 32)
    calls: dict[str, Any] = {}

    class _StubClient:
        def __init__(self, **kwargs: Any) -> None:
            calls["init"] = kwargs

        def approve(self, _amount: int) -> str:
            return "0xapprove"

        def top_up(self, _strategy_id: str, _amount: int) -> str:
            return "0xtopup"

    monkeypatch.setattr(strategy_cmd, "StakeClient", _StubClient)
    result = runner.invoke(
        strategy_cmd.app,
        [
            "stake",
            "top-up",
            "--strategy-id",
            "0x" + "11" * 20,
            "--amount",
            "100",
            "--yes",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "0xtopup" in result.output
    assert calls["init"]["rpc_url"] == "http://stub"


def test_stake_live_requires_keys(deployments_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Make sure live mode trips on missing operator key when neither flag
    # nor env var is set — protects against accidental no-op submissions.
    # We only assert on exit_code because Typer/Click route the
    # BadParameter message through Rich, which writes to a separate
    # stderr stream and renders into a panel whose wrapping varies by
    # terminal width — both make substring matching on result.output
    # fragile across Python/Click versions.
    monkeypatch.delenv("KITE_RPC_URL", raising=False)
    monkeypatch.delenv("OPERATOR_PK", raising=False)
    result = runner.invoke(
        strategy_cmd.app,
        [
            "stake",
            "top-up",
            "--strategy-id",
            "0x" + "11" * 20,
            "--amount",
            "100",
        ],
    )
    assert result.exit_code != 0
    # Sanity: it must be a UsageError-class abort (Click exits 2), not a
    # crash (which would be exit 1 with a Python traceback).
    assert result.exit_code == 2


# ── helios test-proof ──────────────────────────────────────────────


def test_test_proof_round_trip(
    deployments_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = tmp_path / "trade.json"
    spec.write_text(
        json.dumps(
            {
                "strategyClass": "momentum_v1",
                "witnessInputs": {"x": "1"},
                "declaredClass": "momentum_v1",
            }
        )
    )

    posted: dict[str, Any] = {}

    class _FakeResp:
        status_code = 200
        text = ""

        @staticmethod
        def json() -> dict[str, Any]:
            return {
                "proof": {
                    "pi_a": ["1", "2", "1"],
                    "pi_b": [["3", "4"], ["5", "6"], ["1", "0"]],
                    "pi_c": ["7", "8", "1"],
                },
                "publicSignals": ["10", "20"],
            }

    def fake_post(url: str, json: dict[str, Any], timeout: float) -> _FakeResp:
        posted["url"] = url
        posted["body"] = json
        return _FakeResp()

    monkeypatch.setattr(strategy_cmd.httpx, "post", fake_post)

    captured: dict[str, Any] = {}

    class _FakeReader:
        def __init__(self, *, rpc_url: str, verifier_address: str) -> None:
            captured["rpc_url"] = rpc_url
            captured["verifier"] = verifier_address

        def verify(self, declared_class: bytes, proof: bytes, public_inputs: list[int]) -> bool:
            captured["declared_class"] = declared_class
            captured["proof_len"] = len(proof)
            captured["public_inputs"] = public_inputs
            return True

    # `VerifierReader` is bound at import time on the strategy module —
    # patch the binding the command actually calls.
    monkeypatch.setattr(strategy_cmd, "VerifierReader", _FakeReader)

    result = runner.invoke(
        strategy_cmd.app,
        [
            "test-proof",
            "--trade",
            str(spec),
            "--rpc-url",
            "http://anvil:8545",
        ],
    )
    assert result.exit_code == 0, result.output
    assert posted["url"].endswith("/prove")
    assert posted["body"]["strategyClass"] == "momentum_v1"
    assert captured["proof_len"] == 256
    assert captured["public_inputs"] == [10, 20]
    # Pinned to ClassIds.MOMENTUM_V1 in contracts/src/ClassIds.sol
    # (Poseidon-derived bytes32, BN254-fit).
    assert (
        captured["declared_class"].hex()
        == "2a9aa442064b635baec37a7a259282faa5563a653a8325378d5676c6f04bc9dd"
    )


def test_test_proof_skip_onchain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    spec = tmp_path / "trade.json"
    spec.write_text(
        json.dumps(
            {
                "strategyClass": "momentum_v1",
                "witnessInputs": {"x": "1"},
            }
        )
    )

    class _FakeResp:
        status_code = 200
        text = ""

        @staticmethod
        def json() -> dict[str, Any]:
            return {
                "proof": {
                    "pi_a": ["1", "2", "1"],
                    "pi_b": [["3", "4"], ["5", "6"], ["1", "0"]],
                    "pi_c": ["7", "8", "1"],
                },
                "publicSignals": [],
            }

    monkeypatch.setattr(strategy_cmd.httpx, "post", lambda url, json, timeout: _FakeResp())

    result = runner.invoke(
        strategy_cmd.app,
        ["test-proof", "--trade", str(spec), "--skip-onchain"],
    )
    assert result.exit_code == 0, result.output
    assert "skip-onchain" in result.output


def test_test_proof_prover_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    spec = tmp_path / "trade.json"
    spec.write_text(json.dumps({"strategyClass": "momentum_v1", "witnessInputs": {}}))

    class _FakeResp:
        status_code = 503
        text = "snarkjs degraded"

    monkeypatch.setattr(strategy_cmd.httpx, "post", lambda url, json, timeout: _FakeResp())

    result = runner.invoke(
        strategy_cmd.app,
        ["test-proof", "--trade", str(spec), "--skip-onchain"],
    )
    assert result.exit_code == 2
