# Vercel deployment notes

The `frontend/` workspace deploys to Vercel. Production tracks `main`; PRs get automatic preview deployments.

## Project

- **Name:** `helios-frontend`
- **Project ID:** `prj_HGOWeYcf3UPNRdWp7ElpI0rm9ufl`
- **Team ID:** `team_0J6spXsEpueRNcQs7lx10M4U` (personal `emark-cloud` scope)
- **Linked repo:** `emark-cloud/helios`, production branch `main`
- **Root directory:** `frontend`
- **Framework preset:** Next.js (auto-detected)
- **Plan:** Hobby (1 concurrent build, fine for Phase 0–4)

## Token

`VERCEL_TOKEN` in `.env` is a personal API token scoped to the full account. Used by:

- CI (Phase 6+) for deploy hooks if we ever want to bypass GitHub-driven builds.
- Local `vercel` CLI invocations against this project from this machine.

Token is **not committed** — `.env` is gitignored. Rotate via https://vercel.com/account/tokens.

## How deploys land

- Push to `main` → production deploy at `helios-frontend.vercel.app` (custom domain TBD in Phase 6).
- Open a PR against `main` → preview deploy at `helios-frontend-<hash>-emark-clouds-projects.vercel.app`. Vercel comments the URL on the PR.
- No manual `vercel deploy` calls needed for the normal loop.

## Environment variables

Frontend env vars (`NEXT_PUBLIC_*`) must be configured in the Vercel dashboard, not in `.env` — that file is local-only. Set them at:

https://vercel.com/emark-clouds-projects/helios-frontend/settings/environment-variables

Vars to add as Phase 1 lands:

- `NEXT_PUBLIC_KITE_CHAIN_ID` = `2368`
- `NEXT_PUBLIC_GOLDSKY_ENDPOINT` (filled when Phase 1 subgraph deploys)
- `NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID`

## CLI quickstart (optional)

```bash
npx --yes vercel@latest --token "$VERCEL_TOKEN" --scope emark-cloud projects ls
npx --yes vercel@latest --token "$VERCEL_TOKEN" --scope emark-cloud inspect helios-frontend
```

A pinned `vercel` devDep isn't worth it for Phase 0 — the GitHub integration drives all real deploys. Add one if/when CI grows direct deploy steps.
