#!/usr/bin/env bash
# Helios — circuit constraint-budget gate.
#
# For each compiled circuit under build/<name>/<name>.r1cs, compares the
# non-linear constraint count against the BUDGET_<name> declared in the
# Makefile. Fails if any circuit exceeds 90% of its budget so we get an
# audible signal long before we crash into the PTAU 16 ceiling.
#
# Run from circuits/ (Makefile target `check-constraints` does this).

set -euo pipefail

cd "$(dirname "$0")/.."

# (name, budget) pairs — keep in sync with the Makefile BUDGET_* vars.
declare -A BUDGETS=(
  [momentum_v1]=20000
  [mean_reversion_v1]=20000
  [yield_rotation_v1]=15000
)

THRESHOLD_PCT=90
RC=0

for name in "${!BUDGETS[@]}"; do
  r1cs="build/${name}/${name}.r1cs"
  budget="${BUDGETS[$name]}"
  if [[ ! -f "$r1cs" ]]; then
    echo "skip ${name}: no compiled R1CS at ${r1cs}"
    continue
  fi

  # `snarkjs r1cs info` prints "# of Constraints: N" — capture N. The
  # log line is wrapped in ANSI colour codes, so strip them first.
  count=$(npx --no-install snarkjs r1cs info "$r1cs" 2>/dev/null \
    | sed -E 's/\x1b\[[0-9;]*m//g' \
    | awk '/# of Constraints:/ { print $NF; exit }')

  if [[ -z "$count" ]]; then
    echo "ERROR ${name}: could not parse constraint count from snarkjs"
    RC=1
    continue
  fi

  ceiling=$(( budget * THRESHOLD_PCT / 100 ))
  pct=$(( count * 100 / budget ))
  if (( count > ceiling )); then
    printf 'FAIL  %-22s %6d / %6d (%d%%) — over %d%% of budget\n' \
      "$name" "$count" "$budget" "$pct" "$THRESHOLD_PCT"
    RC=1
  else
    printf 'ok    %-22s %6d / %6d (%d%%)\n' \
      "$name" "$count" "$budget" "$pct"
  fi
done

exit $RC
