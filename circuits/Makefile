# Helios circuit build.
#
# Usage:
#   make             # build every circuit (hello + phase-1 stubs)
#   make hello       # build only the Phase 0 hello circuit
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

# PTAU power. Phase 0 defaults to 12 (≈4k constraints, seconds to ceremony) so
# the hello circuit test is fast in CI. Phase 1+ class circuits use PTAU 16
# (≤65k constraints): build with `make PTAU_POWER=16 ptau` before those circuits.
PTAU_POWER  ?= 12
PTAU_FILE   := $(PTAU_DIR)/pot$(PTAU_POWER)_final.ptau

# Circuits shipped by Helios. Each name matches the .circom file name (without .circom).
CIRCUITS := hello

# ────────────────────────────────────────────────────────────
# High-level targets
# ────────────────────────────────────────────────────────────
.PHONY: all clean test ptau $(CIRCUITS)

all: $(CIRCUITS)

clean:
	rm -rf $(BUILD_DIR)
	find $(CONTRACTS_VERIFIERS_DIR) -name 'HelloVerifier.sol' -delete 2>/dev/null || true

test: all
	$(NODE) scripts/verify-hello.js

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
define CIRCUIT_template
$(1): $(BUILD_DIR)/$(1)/$(1).zkey $(BUILD_DIR)/$(1)/verification_key.json $(CONTRACTS_VERIFIERS_DIR)/$(shell echo $(1) | sed 's/.*/\u&/')Verifier.sol

$(BUILD_DIR)/$(1)/$(1).r1cs $(BUILD_DIR)/$(1)/$(1).wasm: $(1).circom
	@mkdir -p $(BUILD_DIR)/$(1)
	$(CIRCOM) $(1).circom --r1cs --wasm --sym -o $(BUILD_DIR)/$(1)
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

$(CONTRACTS_VERIFIERS_DIR)/$(shell echo $(1) | sed 's/.*/\u&/')Verifier.sol: $(BUILD_DIR)/$(1)/$(1).zkey
	@mkdir -p $(CONTRACTS_VERIFIERS_DIR)
	$(SNARKJS) zkey export solidityverifier $(BUILD_DIR)/$(1)/$(1).zkey \
		$(CONTRACTS_VERIFIERS_DIR)/$(shell echo $(1) | sed 's/.*/\u&/')Verifier.sol
	@# snarkjs names the contract "Groth16Verifier"; rename for clarity.
	@sed -i 's/contract Groth16Verifier/contract $(shell echo $(1) | sed 's/.*/\u&/')Verifier/' \
		$(CONTRACTS_VERIFIERS_DIR)/$(shell echo $(1) | sed 's/.*/\u&/')Verifier.sol
endef

$(foreach circuit,$(CIRCUITS),$(eval $(call CIRCUIT_template,$(circuit))))
