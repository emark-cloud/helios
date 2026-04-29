# Helios circuit build.
#
# Usage:
#   make             # build every circuit
#   make test        # run circuit unit tests via node
#   make clean       # wipe build/
#
# Each circuit compiles to .r1cs, .wasm, and a Groth16 .zkey, plus a Solidity
# Verifier that is copied into contracts/src/verifiers/.

CIRCOM      ?= circom
SNARKJS     ?= snarkjs
NODE        ?= node
BUILD_DIR   := build
PTAU_DIR    := ptau
CONTRACTS_VERIFIERS_DIR := ../contracts/src/verifiers

# PTAU power. Phase 1+ class circuits use PTAU 16 (≤65k constraints):
# build with `make PTAU_POWER=16 ptau` before those circuits.
PTAU_POWER  ?= 16
PTAU_FILE   := $(PTAU_DIR)/pot$(PTAU_POWER)_final.ptau

# Circuits shipped by Helios. Each name matches the .circom file name (without .circom).
CIRCUITS := momentum_v1 mean_reversion_v1 yield_rotation_v1

# Per-circuit constraint budgets (non-linear). check-constraints fails if a
# compiled .r1cs exceeds 90% of these. Bumping a budget is a deliberate act:
# update Helios.md §9.4 alongside it. PTAU 16 hard-caps total at 65 535.
BUDGET_momentum_v1        := 20000
BUDGET_mean_reversion_v1  := 20000
BUDGET_yield_rotation_v1  := 15000

# ────────────────────────────────────────────────────────────
# High-level targets
# ────────────────────────────────────────────────────────────
.PHONY: all clean test ptau check-constraints \
        test-momentum test-mean-reversion test-yield-rotation \
        $(CIRCUITS)

all: $(CIRCUITS)

clean:
	rm -rf $(BUILD_DIR)

# Witness-generation tests build .wasm only (skip zkey/PTAU so this runs
# fast in CI before the full PTAU 16 ceremony is needed).
test: test-momentum test-mean-reversion test-yield-rotation

test-momentum: $(BUILD_DIR)/momentum_v1/momentum_v1.wasm
	$(NODE) --test test/momentum_v1.test.js

test-mean-reversion: $(BUILD_DIR)/mean_reversion_v1/mean_reversion_v1.wasm
	$(NODE) --test test/mean_reversion_v1.test.js

test-yield-rotation: $(BUILD_DIR)/yield_rotation_v1/yield_rotation_v1.wasm
	$(NODE) --test test/yield_rotation_v1.test.js

# Verifies every compiled .r1cs is within 90% of its declared BUDGET_*.
# Run after `make all` (or any per-circuit target that produces .r1cs).
check-constraints:
	@bash scripts/check_constraints.sh

# ────────────────────────────────────────────────────────────
# Powers of Tau
# ────────────────────────────────────────────────────────────
ptau: $(PTAU_FILE)

$(PTAU_FILE):
	@echo "→ Generating Powers of Tau (power $(PTAU_POWER))"
	@mkdir -p $(PTAU_DIR)
	$(SNARKJS) powersoftau new bn128 $(PTAU_POWER) $(PTAU_DIR)/pot$(PTAU_POWER)_0000.ptau -v
	@ENTROPY=$$(head -c 32 /dev/urandom | xxd -p -c 64) && \
		$(SNARKJS) powersoftau contribute $(PTAU_DIR)/pot$(PTAU_POWER)_0000.ptau \
		$(PTAU_DIR)/pot$(PTAU_POWER)_0001.ptau --name="helios-local-phase0" -v -e="$$ENTROPY"
	$(SNARKJS) powersoftau prepare phase2 $(PTAU_DIR)/pot$(PTAU_POWER)_0001.ptau $(PTAU_FILE) -v
	@rm -f $(PTAU_DIR)/pot$(PTAU_POWER)_0000.ptau $(PTAU_DIR)/pot$(PTAU_POWER)_0001.ptau

# ────────────────────────────────────────────────────────────
# Per-circuit build
# ────────────────────────────────────────────────────────────
# Convert snake_case to PascalCase for the Solidity verifier name:
# momentum_v1 → MomentumV1, mean_reversion_v1 → MeanReversionV1.
verifier_name = $(shell echo $(1) | python3 -c "import sys; print(''.join(p.capitalize() for p in sys.stdin.read().strip().split('_')))")Verifier

define CIRCUIT_template
$(1): $(BUILD_DIR)/$(1)/$(1).zkey $(BUILD_DIR)/$(1)/verification_key.json $(CONTRACTS_VERIFIERS_DIR)/$(call verifier_name,$(1)).sol

$(BUILD_DIR)/$(1)/$(1).r1cs $(BUILD_DIR)/$(1)/$(1).wasm: $(1).circom
	@mkdir -p $(BUILD_DIR)/$(1)
	$(CIRCOM) $(1).circom --r1cs --wasm --sym -l node_modules -o $(BUILD_DIR)/$(1)
	mv $(BUILD_DIR)/$(1)/$(1)_js/$(1).wasm $(BUILD_DIR)/$(1)/$(1).wasm
	rm -rf $(BUILD_DIR)/$(1)/$(1)_js

$(BUILD_DIR)/$(1)/$(1).zkey: $(BUILD_DIR)/$(1)/$(1).r1cs $(PTAU_FILE)
	$(SNARKJS) groth16 setup $(BUILD_DIR)/$(1)/$(1).r1cs $(PTAU_FILE) $(BUILD_DIR)/$(1)/$(1)_0000.zkey
	@ENTROPY=$$$$(head -c 32 /dev/urandom | xxd -p -c 64) && \
		$(SNARKJS) zkey contribute $(BUILD_DIR)/$(1)/$(1)_0000.zkey $(BUILD_DIR)/$(1)/$(1).zkey \
		--name="helios-local" -v -e="$$$$ENTROPY"
	@rm -f $(BUILD_DIR)/$(1)/$(1)_0000.zkey

$(BUILD_DIR)/$(1)/verification_key.json: $(BUILD_DIR)/$(1)/$(1).zkey
	$(SNARKJS) zkey export verificationkey $(BUILD_DIR)/$(1)/$(1).zkey $(BUILD_DIR)/$(1)/verification_key.json

$(CONTRACTS_VERIFIERS_DIR)/$(call verifier_name,$(1)).sol: $(BUILD_DIR)/$(1)/$(1).zkey
	@mkdir -p $(CONTRACTS_VERIFIERS_DIR)
	$(SNARKJS) zkey export solidityverifier $(BUILD_DIR)/$(1)/$(1).zkey \
		$(CONTRACTS_VERIFIERS_DIR)/$(call verifier_name,$(1)).sol
	@# snarkjs names the contract "Groth16Verifier"; rename for clarity.
	@sed -i 's/contract Groth16Verifier/contract $(call verifier_name,$(1))/' \
		$(CONTRACTS_VERIFIERS_DIR)/$(call verifier_name,$(1)).sol
endef

$(foreach circuit,$(CIRCUITS),$(eval $(call CIRCUIT_template,$(circuit))))
