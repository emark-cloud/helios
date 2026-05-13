"""Regression for the CXR VPS NavSignatureInvalid bug (2026-05-13).

The strategy runtime's `nav_oracle_pk` field is declared as
`Field(default="", validation_alias="NAV_ORACLE_PK")`. pydantic-settings'
`validation_alias` **takes precedence over** the model's `env_prefix`, so
the runtime reads the *unprefixed* env var only — `MOMENTUM_NAV_ORACLE_PK`
/ `MEAN_REV_NAV_ORACLE_PK` / `YIELD_ROT_NAV_ORACLE_PK` are silently
ignored.

The Phase-5 CXR-3 compose entries for `momentum_v1_base` and
`mean_reversion_v1_base` shipped with the prefixed keys, so both Base
containers inherited the *Kite* `NAV_ORACLE_PK` from `/srv/helios/.env`
and reverted `NavSignatureInvalid()` (selector 0x201a422e) on every NAV
tick for two days before the bug was found.

This test pins three invariants:

1. The unprefixed `NAV_ORACLE_PK` is exactly the validation_alias each
   strategy Settings class declares for nav_oracle_pk (catches an alias
   rename that would silently re-break the compose entries).
2. No service block in `deploy/docker-compose.prod.yml` sets a prefixed
   `*_NAV_ORACLE_PK` key in its `environment:` (those are the typos that
   cost the Base bring-up).
3. Every remote-chain strategy service (a service whose name ends in
   `_base` or `_arb`) overrides `NAV_ORACLE_PK` explicitly — otherwise it
   inherits the Kite key from `env_file` and reverts.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPOSE_FILE = REPO_ROOT / "deploy" / "docker-compose.prod.yml"

# Strategy services whose runtime imports `nav_oracle_pk` via the
# unprefixed `NAV_ORACLE_PK` alias. The prefix on the LHS is the
# `env_prefix` setting on the Settings class — only meaningful for fields
# that DON'T set a validation_alias (e.g. operator_pk).
STRATEGY_SETTINGS_MODULES = [
    ("momentum_v1", "MOMENTUM_"),
    ("mean_reversion_v1", "MEAN_REV_"),
    ("yield_rotation_v1", "YIELD_ROT_"),
]


def _load_compose() -> dict:
    return yaml.safe_load(COMPOSE_FILE.read_text())


def test_nav_oracle_pk_alias_is_unprefixed() -> None:
    """Each strategy Settings declares nav_oracle_pk with
    validation_alias='NAV_ORACLE_PK'. If a future refactor adds a prefix,
    this test fails so the compose entries can be updated in lockstep."""
    from importlib import import_module

    for module_name, expected_prefix in STRATEGY_SETTINGS_MODULES:
        try:
            settings_cls = import_module(f"{module_name}.service").Settings
        except ImportError:
            # Not every workspace member is importable from this test's
            # own venv (mean_reversion + yield_rotation have separate
            # pyprojects); skip cleanly when their package isn't on
            # sys.path so the test still locks the momentum invariant.
            continue
        fields = settings_cls.model_fields
        assert "nav_oracle_pk" in fields, f"{module_name} Settings missing nav_oracle_pk"
        alias = fields["nav_oracle_pk"].validation_alias
        assert alias == "NAV_ORACLE_PK", (
            f"{module_name}.Settings.nav_oracle_pk validation_alias = {alias!r}; "
            f"must remain 'NAV_ORACLE_PK' (unprefixed) so docker-compose's "
            f"`NAV_ORACLE_PK:` override binds correctly. If you intentionally "
            f"renamed it, also update `deploy/docker-compose.prod.yml` for "
            f"every {module_name} service (Kite + remote chains)."
        )
        # Cross-check: env_prefix is what we expect — locks the prefix
        # rename so operator_pk-style fields (which DO use the prefix)
        # don't drift away from the compose entries.
        assert settings_cls.model_config["env_prefix"] == expected_prefix, (
            f"{module_name}.Settings env_prefix = "
            f"{settings_cls.model_config['env_prefix']!r}; expected {expected_prefix!r}"
        )


def test_compose_has_no_prefixed_nav_oracle_pk_overrides() -> None:
    """A `<PREFIX>_NAV_ORACLE_PK:` override in `environment:` is always a
    typo — the runtime never reads it. Catches the original CXR-3 bug
    and any copy-paste re-introduction."""
    compose = _load_compose()
    bad_keys = {
        "MOMENTUM_NAV_ORACLE_PK",
        "MEAN_REV_NAV_ORACLE_PK",
        "YIELD_ROT_NAV_ORACLE_PK",
    }
    offenders: list[str] = []
    for svc_name, svc in (compose.get("services") or {}).items():
        env = svc.get("environment") if isinstance(svc, dict) else None
        if not env:
            continue
        if isinstance(env, list):
            keys = {entry.split("=", 1)[0] for entry in env if isinstance(entry, str)}
        else:
            keys = set(env.keys())
        for k in keys & bad_keys:
            offenders.append(f"{svc_name}.environment.{k}")
    assert not offenders, (
        "Prefixed *_NAV_ORACLE_PK in compose `environment:` blocks — runtime "
        "ignores these (validation_alias='NAV_ORACLE_PK'). Use the unprefixed "
        f"key. Offenders: {offenders}"
    )


_REMOTE_CHAIN_PATTERN = re.compile(r".*_(base|arb)$")


def _strategy_services(compose: dict) -> dict[str, dict]:
    """Return only strategy services (mom/mr/yr family). Skips infra
    services (postgres, redis, sentinel, oracle, prover, ...)."""
    strategy_prefixes = ("momentum_v1", "mean_reversion_v1", "yield_rotation_v1")
    services = compose.get("services") or {}
    return {
        name: svc
        for name, svc in services.items()
        if isinstance(svc, dict) and name.startswith(strategy_prefixes)
    }


def test_remote_strategy_services_override_nav_oracle_pk() -> None:
    """For any strategy service targeting a non-Kite chain (suffix `_base`
    or `_arb`), `NAV_ORACLE_PK` MUST be explicitly overridden in the
    `environment:` block. Otherwise the container inherits the Kite key
    from `env_file: /srv/helios/.env` and the EIP-712 signature recovers
    to the wrong navOracle EOA.

    Exception: a remote service whose vault was deployed with
    `navOracle = <deployer EOA>` legitimately shares the Kite key. To
    skip this test for that service, add it to `_SHARED_KEY_SERVICES`
    below with a one-line comment citing the on-chain navOracle slot.
    """
    # yr.arb's manifest.operator and navOracle both equal the deployer
    # EOA `0xECf5e30F091D1db7c7b0ef26634a71d46DC9Bb25`, which is also
    # the Kite yr navOracle. The Kite `NAV_ORACLE_PK` in env_file
    # signs for the same address on both chains (verified via
    # cast call yield_rotation_v1_arb on 2026-05-13).
    _SHARED_KEY_SERVICES = {"yield_rotation_v1_arb"}

    compose = _load_compose()
    missing: list[str] = []
    for name, svc in _strategy_services(compose).items():
        if not _REMOTE_CHAIN_PATTERN.match(name):
            continue
        if name in _SHARED_KEY_SERVICES:
            continue
        env = svc.get("environment") or {}
        if isinstance(env, list):
            keys = {entry.split("=", 1)[0] for entry in env if isinstance(entry, str)}
        else:
            keys = set(env.keys())
        if "NAV_ORACLE_PK" not in keys:
            missing.append(name)
    assert not missing, (
        "Remote-chain strategy services without an explicit NAV_ORACLE_PK "
        "override: "
        f"{missing}. Add `NAV_ORACLE_PK: ${{<PREFIX>_<CHAIN>_NAV_ORACLE_PK}}` "
        "to the service's `environment:` block, or — if the deploy intentionally "
        "shares the Kite key — extend `_SHARED_KEY_SERVICES` with a one-line "
        "justification."
    )


def test_compose_kite_strategy_services_use_unprefixed_override_correctly() -> None:
    """Sanity-check the Kite-side override shape. Each Kite service that
    overrides `NAV_ORACLE_PK` (currently only `momentum_v1` +
    `mean_reversion_v1`) must source it from the *prefixed* shell var
    (`MOMENTUM_NAV_ORACLE_PK`, `MEAN_REV_NAV_ORACLE_PK`) in env_file —
    that's how per-class dedicated EOAs (WS9 #9) reach the right
    container without container env collisions."""
    compose = _load_compose()
    expected_sources = {
        "momentum_v1": "${MOMENTUM_NAV_ORACLE_PK}",
        "mean_reversion_v1": "${MEAN_REV_NAV_ORACLE_PK}",
    }
    for svc_name, expected in expected_sources.items():
        svc = compose["services"].get(svc_name)
        if svc is None:
            pytest.skip(f"{svc_name} not in compose — env may have been pruned")
        env = svc.get("environment") or {}
        if isinstance(env, list):
            kv = dict(entry.split("=", 1) for entry in env if "=" in entry)
        else:
            kv = {k: str(v) for k, v in env.items()}
        # `NAV_ORACLE_PK` may legitimately be absent on Kite services if
        # the env_file value works directly. The invariant is only:
        # *when* the Kite service overrides it, the source matches the
        # per-class shell var.
        if "NAV_ORACLE_PK" in kv:
            assert kv["NAV_ORACLE_PK"] == expected, (
                f"{svc_name} overrides NAV_ORACLE_PK with {kv['NAV_ORACLE_PK']!r}; "
                f"expected {expected!r} (the per-class shell var in env_file)."
            )
