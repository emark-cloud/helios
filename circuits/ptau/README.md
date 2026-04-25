# Powers of Tau

Helios uses **PTAU 16** (bn128, ≤65k constraints) for the Phase 0–2 circuit toolchain.
All three v1 class circuits (`momentum_v1`, `mean_reversion_v1`, `yield_rotation_v1`)
target ≤20k constraints, so the PTAU 16 headroom is comfortable.

## Local ceremony (dev only)

For local development and CI, a **single-contributor local ceremony** is fine:

```bash
make -C .. ptau
```

This generates `pot16_final.ptau` with one contribution keyed by your shell's
`$RANDOM`. **Do not use local-ceremony artifacts in production.**

## Production path (post-hackathon)

Before any real capital flows, swap this artifact for one of:

1. **Hermez ceremony** — widely-reviewed, many contributors, trusted-minimally setup.
2. **Perpetual Powers of Tau** — actively maintained, large contributor set.
3. **Helios-specific ceremony** — if we run our own, document the contributor list
   and publish transcripts alongside the zkey.

See `Helios.md §9.5` and `§15.1` for the full trust-model note.

## Files

- `pot16_final.ptau` — generated; gitignored. Run `make ptau` to create.
- `README.md` — this file.
