# External-contributor smoke

Closes Phase 2 acceptance gate **"External contributor could publish
a strategy using only the SDK + public docs"** (`TODO.md` line 302,
`docs/phase2-plan.md` WS6 step 8).

## What it proves

A fresh contributor with only Docker installed can:

1. `pip install helios-strategy-sdk helios-trader-cli`
2. Write a tiny `StrategyAgent` subclass
3. Run `helios backtest` and `helios simulate` against it

> **Why `helios-trader-cli` and not `helios-cli`?** The bare
> `helios-cli` name is squatted on real PyPI by an unrelated project
> (LLM-usage tracker, `helios-cli` 0.1.0). Helios publishes its CLI
> as `helios-trader-cli` so `pip install` is unambiguous. The binary
> on disk is still called `helios`; the import path is still
> `helios_cli`.

…without ever cloning the Helios monorepo or touching its dev
tooling. The smoke runs all three steps inside a clean
`python:3.12-slim` container as a non-root user.

## Quick start

```bash
./docs/external-contributor/smoke.sh
```

That builds the image from this repo's local workspace
(`INSTALL_MODE=local`, the default) and runs `helios backtest` +
`helios simulate` against `examples/minimal_momentum.py`. Exits 0 on
success. No network publish needed.

## Install modes

The Dockerfile takes an `INSTALL_MODE` build-arg. The smoke script
forwards `$INSTALL_MODE` and `$WHEEL_BASE_URL` from the environment.

| Mode | When to use | What it does |
|---|---|---|
| `local` (default) | Working in the repo, validating the install graph. | COPYs the four workspace packages and pip-installs each one. |
| `release` | Demonstrating the external-contributor flow against a real published artifact. The canonical PR5.B path. | Curls the four wheels from `${WHEEL_BASE_URL}` and pip-installs via `--find-links` so transitive deps still resolve from PyPI. |
| `testpypi` | Once `helios-trader-cli`, `helios-allocator-sdk`, `helios-contracts-abi` have their test.pypi.org trusted-publisher entries (web-UI gated). | pip-installs `helios-strategy-sdk` + `helios-trader-cli` from test-PyPI with the public PyPI fallback. |

### `INSTALL_MODE=release` against a GitHub Release

```bash
INSTALL_MODE=release \
SDK_VERSION=0.1.0 \
WHEEL_BASE_URL=https://github.com/emark-cloud/helios/releases/download/sdk-v0.1.0/ \
./docs/external-contributor/smoke.sh
```

The `release-wheels.yml` workflow builds and uploads the four wheels
on every `sdk-v*` tag. The release URL is stable and predictable, so
external contributors install via:

```bash
pip install \
    --find-links https://github.com/emark-cloud/helios/releases/download/sdk-v0.1.0/ \
    --extra-index-url https://pypi.org/simple/ \
    helios-trader-cli
```

That single command resolves the four workspace wheels by name
(via `--find-links`) and pulls every transitive dep (numpy / pydantic
/ web3 / …) from public PyPI.

### `INSTALL_MODE=testpypi` (future)

```bash
INSTALL_MODE=testpypi SDK_VERSION=0.1.0 ./docs/external-contributor/smoke.sh
```

Only `helios-strategy-sdk` is published to test-PyPI today.
`helios-trader-cli` and friends will join once their trusted-publisher
entries are registered on test.pypi.org. The `release` mode above is
the unblocked alternative until then.

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
