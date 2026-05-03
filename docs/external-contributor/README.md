# External-contributor smoke

Closes Phase 2 acceptance gate **"External contributor could publish
a strategy using only the SDK + public docs"** (`TODO.md` line 302,
`docs/phase2-plan.md` WS6 step 8).

## What it proves

A fresh contributor with only Docker installed can:

1. `pip install helios-strategy-sdk` (alongside `helios-cli`)
2. Write a tiny `StrategyAgent` subclass
3. Run `helios backtest` and `helios simulate` against it

…without ever cloning the Helios monorepo or touching its dev
tooling. The smoke runs all three steps inside a clean
`python:3.12-slim` container as a non-root user.

## Quick start

```bash
./docs/external-contributor/smoke.sh
```

That builds the image (PR5.A: from this repo's local workspace) and
runs `helios backtest` + `helios simulate` against
`examples/minimal_momentum.py`. Exits 0 on success.

## Switching to test-PyPI (PR5.B, gated on OIDC setup)

Once the test.pypi.org trusted publisher is registered (see
`docs/ws6-pr4-pr5-plan.md` and memory `project_testpypi_oidc_setup.md`)
and the first `sdk-v*` tag publishes the wheels, flip the smoke to
install from test-PyPI:

```bash
INSTALL_MODE=testpypi SDK_VERSION=0.1.0 ./docs/external-contributor/smoke.sh
```

This bypasses the workspace COPY entirely and pip-installs from
test-PyPI with the public PyPI fallback for transitive deps
(numpy/pydantic/web3/…). That run is the canonical demonstration of
the spec acceptance gate.

## What's intentionally *not* in the smoke

- **`helios test-proof`** needs a live prover service + circuit
  artifacts in `circuits/build/<class>/`. The full proof round-trip
  is exercised by the WS6 e2e (`scripts/e2e-scenario-phase2.sh`)
  rather than a one-shot smoke. The `examples/momentum_witness.json`
  fixture stays so contributors can run `helios test-proof` manually
  against any prover (`PROVER_URL=… helios test-proof --trade
  examples/momentum_witness.json --skip-onchain`).
- **`helios deploy`** ships your strategy to a real VPS — by design
  it requires real SSH credentials.
- **`helios stake`** speaks to a real RPC + operator key — same
  rationale.

The shipped smoke is the smallest set of commands a brand-new
contributor needs in order to *evaluate* whether they want to commit
to the full operator workflow. The full workflow is documented in
`docs/operator-guide.md`.

## Files

```
docs/external-contributor/
├── Dockerfile             — python:3.12-slim + INSTALL_MODE switch
├── .dockerignore          — trims build context to four packages
├── smoke.sh               — entrypoint
├── README.md              — this file
└── examples/
    ├── minimal_momentum.py    — minimal StrategyAgent subclass
    └── momentum_witness.json  — sample trade spec for test-proof
```
