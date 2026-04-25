"""Per-class strategy bases.

Each declared strategy class gets a base class here that enforces the
class's invariants in the SDK and wires the matching circuit at the
prover-service layer. Phase 0 ships only the registry of class names;
Phase 1 backfills momentum_v1; Phase 2 adds the rest.
"""

KNOWN_CLASSES: tuple[str, ...] = (
    "momentum_v1",
    "mean_reversion_v1",
    "yield_rotation_v1",
)
