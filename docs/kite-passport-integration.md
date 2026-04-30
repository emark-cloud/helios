# Kite Passport / AA SDK / x402 — Integration Proposal

**Status:** Accepted 2026-04-30. Recommendations adopted: Phase 1 = C + E + F; Phase 2 adds G. Q1–Q3 spike runs first.
**Author:** Claude (drafted 2026-04-30 from `docs.gokite.ai/kite-agent-passport/*` and `docs.gokite.ai/kite-chain/account-abstraction-sdk`)
**Supersedes:** `docs/kite-passport-notes.md` once decisions land. Notes doc is kept until the swap-out lands.
**Related spec sections:** `Helios.md` §0 (user flow), §3 (Kite primitives), §6.1 (UserVault), §10 (meta-strategy), §17 (demo script).

---

## 1. Why this exists

`Helios.md` was written against an assumption — that **Kite Passport** is a hierarchical BIP-32 identity primitive (User → Allocator → Strategy session derivation, EIP-1271 verifying the meta-strategy signature, root keys never leaving the user's enclave). That model is repeated throughout the spec (§3.L1, §6.1, §17 threat model, §17 demo script), and the existing `docs/kite-passport-notes.md` is built on it.

Kite mainnet went live **2026-04-28** (chain id 2366). With public docs now stable, the actual surface diverges from the assumed model in ways that touch Helios's user-onboarding contract, the meta-strategy signing flow, and the demo voiceover. This doc resolves that.

## 2. What Kite actually ships

Three distinct things, often conflated:

### 2.1 AA SDK — `gokite-aa-sdk` (npm)
Lower-level developer primitive. Documented at `docs.gokite.ai/kite-chain/account-abstraction-sdk`. Surface:

- Smart-contract wallet creation (`GokiteAASDK`, `getAccountAddress(signer)`)
- Upgradeable vault deployment via proxy
- Spending-rule configuration: budget caps, time windows
- Gasless userOps via a bundler
- Third-party signer integration (Privy, Particle, …)

Not documented (and assumed in the current Helios spec): BIP-32 hierarchical session derivation, EIP-1271 on Passport contracts, native paymaster sponsorship policy. These need to be verified or replaced with explicit equivalents.

### 2.2 Passport — `kpass` CLI + dashboard
Consumer/agent product layered on AA SDK. Built for AI coding agents (Claude Code, Codex, Cursor) to autonomously pay for services. Surface:

- User signup: email + passkey → Passport-managed wallet on Kite, USDC funded via Banxa fiat / `bridge.gokite.ai` / self-custody bridge.
- **Spending sessions**: `kpass agent:session create --task-summary --max-amount-per-tx --max-total-amount --ttl --assets --payment-approach`. Passkey-approved per session.
- Within session: `kpass agent:session use`, `kpass agent:session execute --url --method` for paid HTTP calls.
- `kpass wallet send` for direct transfers; `kpass faucet drop` on testnet.

The session is **not a long-lived signing key**. It's an authorization scope that the Passport infrastructure itself enforces — when its TTL expires or budget is exhausted, the agent loses the ability to spend, no on-chain revocation needed.

### 2.3 x402 — payment protocol
HTTP-level payment negotiation. Documented at `docs.gokite.ai/kite-agent-passport/service-provider-guide`. Flow:

1. Service responds `402 Payment Required` with terms (`payTo`, `maxAmountRequired`, `outputSchema`).
2. Agent attaches signed authorization in `X-Payment` header (drawn from active session).
3. Service calls **Pieverse facilitator** `https://facilitator.pieverse.io` — `POST /v2/verify` then `POST /v2/settle` — to validate and execute.
4. Service returns the requested data.

Scheme on Kite: `gokite-aa`. Testnet USDC contract used in examples: `0x0fF5393387ad2f9f691FD6Fd28e07E3969e27e63`.

## 3. The spec/reality gap

`Helios.md` §0 line 57 ("A user signs **one** meta-strategy") implies a single durable EIP-712 signature that on-chain code verifies and that an Allocator's session is BIP-32-derived from. That story doesn't fit Passport's actual primitive of a TTL- and budget-bounded session approved per-flow via passkey.

Specifically:

| Spec assumption | Reality | Severity |
|---|---|---|
| User signs meta-strategy once via Passport; UserVault verifies via EIP-1271 | Passport gives passkey-approved sessions, not a static signature; EIP-1271 on Passport accounts not documented | **High** — invalidates §6.1 setMetaStrategy flow |
| Allocator session is BIP-32 child of user Passport | AA SDK doesn't document hierarchical derivation; Passport sessions are flat scopes | **High** — invalidates §3 cascade delegation story |
| User keys never leave enclave | True for the passkey, but Passport-managed wallet isn't user-custodial in the same sense | **Medium** — affects threat-model framing |
| `KITE_PASSPORT_SIGNER_PK` env var | Passport doesn't expose raw signer PKs | **Low** — env-name change |
| §17 voiceover: "one MetaMask popup" | UX is now passkey + email + dashboard | **Medium** — re-shoot demo script |
| x402 + Pieverse settlement path | Not in spec at all | **New** — opportunity, not gap |

## 4. Three integration choices

These are **orthogonal**: pick one from §4.1, then independently decide on §4.2 and §4.3.

### 4.1 User-onboarding mechanism (pick one)

**A. Plain AA SDK + EOA signer.** User connects an EOA (MetaMask). We deploy a smart-account UserVault for them via `gokite-aa-sdk`. Spending rules in the AA wallet enforce the meta-strategy. Allocator gets a session key on the AA wallet (this is the part that needs verification — does AA SDK expose session-key delegation, or only spending rules?).
- **Pros:** Closest to the existing spec & contracts; the Allocator-session story still works if AA SDK has session keys; demo retains "one signature" feel via EOA EIP-712.
- **Cons:** Doesn't use Passport at all, so we lose the "uses Kite identity" judging criterion. The Helios.md narrative needs to drop the "Passport delegation chain" framing.

**B. Passport-only onboarding.** User signs up to Passport via `kpass`; their Passport wallet is funded via Banxa/bridge. They `kpass agent:session create` for Helios with `max-total-amount = capital cap`, `ttl = strategy duration`, asset whitelist = USDC. The session authorizes Helios's backend to pull capital into UserVault on their behalf, and to authorize Allocator allocations.
- **Pros:** Strong fit with Kite's product narrative; passkey UX is genuinely cleaner than MetaMask; uses x402-compatible primitives end-to-end.
- **Cons:** "Meta-strategy" semantics need rework — it's no longer a signed declaration that on-chain code verifies, it's a session scope that the off-chain Allocator and Pieverse facilitator jointly enforce. UserVault contract gets simpler (less validation logic), but the **on-chain trust story weakens**: an Allocator going rogue is no longer fully bounded by Solidity, only by the session budget. Need to reconcile with §17 threat model.

**C. Passport for funding, AA SDK for execution (hybrid).** User onboards via Passport; one Passport session funds the UserVault (smart-account, deployed via `gokite-aa-sdk`). From that point on, UserVault enforces meta-strategy via on-chain rules — same contracts as the original spec, no Pieverse facilitator on the trade-execution path. Passport reappears at "top-up" or "rebalance approval" moments.
- **Pros:** Keeps the on-chain trust story intact (rogue Allocator is bounded by Solidity, not by a facilitator). Uses Passport for the parts where it's a real UX win (onboarding, funding) and AA SDK for the parts where on-chain enforcement matters. Best fit with current contract design.
- **Cons:** Two onboarding surfaces to integrate. Funding flow has an extra hop (Passport wallet → UserVault). The "user signs one meta-strategy" line becomes "user approves one Passport session that locks in a meta-strategy" — close enough, but the demo voiceover needs a tweak.

**Recommendation: C.** It preserves the on-chain enforcement story that the §17 threat model leans on, while using Passport where it's actually a UX asset. (B) is tempting for narrative purity but trades real safety for it. (A) bypasses Passport entirely and forfeits the "uses Kite identity" judging criterion.

### 4.2 Allocator → Strategy delegation (pick one)

**D. AA SDK session keys (if available).** Allocator holds a session key on UserVault's AA account, scoped to allowed function selectors and asset whitelist. Strategy operators hold session keys on AllocatorVault.
- **Pros:** Matches §3 cascade story.
- **Cons:** Conditional on AA SDK actually exposing session-key delegation; needs verification (open question Q1 below).

**E. Plain Solidity authorization.** UserVault has `mapping(address => bool) public allowedAllocator`. AllocatorVault has `mapping(address => bool) public allowedStrategy`. No session-key cryptography; just on-chain ACL set by the parent. Revocation = setting the bool false.
- **Pros:** Works regardless of AA SDK feature set; trivially auditable; matches what's already in `contracts/`.
- **Cons:** Loses the "BIP-32 hierarchical, root keys never exposed" narrative. Needs a story for Allocator key rotation.

**Recommendation: E for Phase 1**, with a Phase-2 path to D if AA SDK supports it. Spec language updates from "BIP-32 cascade" to "on-chain ACL cascade" — less novel, but it's what works.

### 4.3 Service-economy integration (binary)

**F. No x402.** Oracle/prover/audit are internal services Helios operates and fronts for free. Status quo.

**G. x402-native paid services.** Oracle, prover, audit, reputation reads expose x402 endpoints. Allocators consume them via Passport sessions. Pieverse facilitator settles. We become a service provider on Kite's agent economy.
- **Pros:** Strong thematic fit; the Allocator paying the prover via x402 is a *headline* demo moment that makes Helios's "agent market" pitch tangible. Aligns with Kite's actual product.
- **Cons:** Each service needs Pieverse-compatible payment middleware. Pricing curves to design (per-snapshot? per-proof? bundled?). External dependency on Pieverse facilitator uptime.

**Recommendation: F for Phase 1, G for Phase 2 demo polish.** Don't ship x402 in the vertical slice — it's not critical-path. Layer it on top in Phase 2 once the core flows are green, specifically targeting the demo's "agent paying agent" moment.

## 5. Phase rollout

**Phase 1 (current):** Choices C + E + F.
- Replace `KITE_PASSPORT_SIGNER_PK` with `KITE_PASSPORT_SESSION_ID` (or equivalent).
- Onboarding flow: `kpass` signup → fund Passport wallet → one passkey-approved session funds UserVault.
- UserVault remains a smart-account, but its meta-strategy enforcement is plain on-chain ACL + spending rules (matches existing contracts).
- Allocator/Strategy delegation = on-chain bool ACLs. No BIP-32.
- Demo voiceover updated: "She approves one passkey session — that's the only thing she does. From here, everything is autonomous on-chain."

**Phase 2:** Add G — convert Oracle, Prover, Audit endpoints to x402; Allocator pays via active Passport session. Pieverse-compatible middleware in `services/oracle`, `services/prover`, `services/reputation`. New demo beat: live x402 settle in the activity feed.

**Phase 5/6:** Promote to mainnet (chain 2366). If AA SDK by then exposes session-key delegation natively, evaluate D for the cascade story. If not, ship E and rewrite the spec language to match.

## 6. Concrete spec & code changes (if proposal accepted)

1. **`Helios.md`** — rewrite §3.L1 ("Identity"), §6.1 (UserVault interface — drop EIP-1271 metaStrategyHash flow, replace with constructor-arg meta-strategy locked at deploy time, settable only by `onlyOwner`), §17 threat model (rogue Allocator bounded by Solidity ACL + AA spending rules, not BIP-32).
2. **`docs/kite-passport-notes.md`** — replace with operational notes for `kpass` CLI + AA SDK, drop BIP-32 swap-in checklist, add session-management runbook.
3. **`.env.example`** — `KITE_PASSPORT_SIGNER_PK` → `KITE_PASSPORT_SESSION_ID` + `KITE_PASSPORT_WALLET_ADDRESS`. Add `PIEVERSE_FACILITATOR_URL` (Phase 2).
4. **`scripts/kite-passport-smoke.mjs`** — rewrite to use `kpass` CLI invocations + `gokite-aa-sdk` for the smart-account side, not the imagined hierarchical derivation.
5. **`contracts/UserVault.sol`** — confirm meta-strategy fields are immutable post-construction (verify; might already be). Drop any EIP-1271 verifier path if present.
6. **`frontend/src/app/onboard/`** — replace MetaMask sign flow with `kpass` deep-link or embedded passkey UX (open question Q3).
7. **`TODO.md`** Phase 0 — flip Passport criterion from "blocked external" to "spec rewrite + integration"; track as a Phase 1 task.

## 7. Spike findings (2026-04-30)

Spike completed via SDK-tarball inspection of `gokite-aa-sdk@1.0.15` (npm), `@gokite-network/auth@0.1.16` (npm), and Kite docs. Live interactive test deferred — SDK type definitions answer the gating questions conclusively.

### Q1 — AA SDK session-key delegation? **No.**

`gokite-aa-sdk` is a thin ERC-4337 client over Kite's bundler + EntryPoint. Surface (`dist/gokite-aa-sdk.d.ts`):
- `GokiteAASDK(network, rpcUrl, bundlerUrl?)` — constructor.
- Account: `getAccountAddress(owner, salt?)`, `getAccountNonce`, `isAccountDeployed`, `buildInitCode`.
- Calls: `buildCallData`, `buildBatchCallData`, `createUserOperation`, `estimateGas`, `sendUserOperation`, `sendUserOperationAndWait`, `sendUserOperationDirectly`, `sendUserOperationWithPayment`, `pollUserOperationStatus`.
- Paymaster: `estimateUserOperation` returns `sponsorshipAvailable`, `remainingSponsorships`, `supportedTokens`. `sendUserOperationWithPayment(...tokenAddress...)` pays gas in ERC-20.
- Re-export: `DelegatorStakingClient` from `staking/staking-example`.

Auth is a flat `SignFunction = (userOpHash) => Promise<string>` callback. **No parent-child delegation, no scoped sub-keys, no EIP-1271 surface.** The "spending rules" mentioned in the docs page are contract-side rules on a separate "agent wallet" contract, not SDK methods. → **Choice E (plain Solidity ACL) confirmed correct.**

### Q2 — Can a Passport session authorize non-x402 contract calls? **Yes — via the SDK directly, not the `kpass` CLI.**

Two surfaces:
- `kpass agent:session execute --url --method` is **HTTP-only** (x402-bound). Useful for agent-pays-paid-service flows (choice G).
- `UserOperationRequest = { target, value?, callData }` in `gokite-aa-sdk` is **fully general** — any contract, any selector. The Passport-managed AA wallet is just an ERC-4337 smart account; it can `userOp → UserVault.deposit(amount)` exactly like any other smart wallet. No x402 wrapping required.

→ **Funding flow under choice C works.** Frontend invokes the SDK to build a `userOp` that calls `USDC.approve(UserVault, amount)` + `UserVault.deposit(amount)` (batched), user signs the userOp hash via Particle, bundler ships it. `kpass` is not involved on the user-onboarding path.

### Q3 — Embeddable Passport widget? **Yes — `@gokite-network/auth`.**

Maintained by `jerry.zhu@gokite.ai` (gokite team). Built on Particle Network (`@particle-network/auth` + `@particle-network/aa` + `@particle-network/provider`). Surface (`dist/index.d.ts`):
- `GokiteNetwork` — orchestrator with `login(LoginOptions)`, `logout()`, `user`, `signin({eoa, aa_address, displayed_name, avatar_url, …})`. Ready/event hooks via `Deferred`.
- `SmartAccount(auth, chain, {entryPointAddress, smartAccountFactoryAddress, secretKey})` — viem-typed AA wallet wrapper.
- `gokiteTestnet` — exported viem `Chain`.

The login surface (`@particle-network/auth`'s `LoginOptions`) covers passkey/email/social. `IdentifyState` returns `aa_address`, which is the Passport AA wallet — same primitive that `gokite-aa-sdk` operates against. → **Frontend `/onboard` can embed this directly; no `kpass` deep-link needed.**

Caveat: package last published 2025-11-01 (≈6 months old as of 2026-04-30). Worth pinning the exact version we test against and watching for a refresh during Phase 4.

### Q4 / Q5 — deferred to Phase 2 G implementation.

Pieverse mainnet/testnet split and canonical mainnet USDC are only material when we wire x402 endpoints (choice G). Punt to Phase 2 demo-polish workstream where the actual settlement happens.

### Implications for the integration plan

1. **Two separate Passport touchpoints, not one.** `/onboard` uses `@gokite-network/auth` (consumer flow); a Phase 2 service-economy lift uses `kpass`-equivalent x402 client libs against `@gokite-network/auth`-issued sessions. Different audiences, different SDKs, both layered on the same AA primitive.
2. **No `curl | bash` install needed for spike or Phase 1.** The frontend is the integration surface. `kpass` only matters when we ship choice G in Phase 2.
3. **Funding flow concrete shape:** frontend calls `sdk.sendUserOperationAndWait(owner, batchRequest)` where `batchRequest = { targets: [USDC, UserVault], callDatas: [approve, deposit] }`. This batches in one userOp, paymaster-sponsored if `sponsorshipAvailable`.
4. **`KITE_PASSPORT_SIGNER_PK` env var stays dead.** Replace with frontend Particle config (project ID, client key) — no service-side env changes for choice C onboarding.
5. **Helios.md §3 "BIP-32 hierarchical, root keys never leave enclave" framing must drop.** Particle holds the EOA, not the user's hardware. The honest framing is "non-custodial via Particle's MPC, scoped to a session-bounded smart account."

## 8. Rejected alternatives

- **"Wait for Kite to ship hierarchical sessions and keep the spec as-written."** Rejected — there's no public roadmap commitment to it, and Phase 1's vertical slice can't block on a feature that may never ship.
- **"Skip Passport, run Helios on plain Kite EOAs."** Rejected — forfeits the "uses Kite identity" judging criterion and weakens the agent-economy framing that's central to the pitch.
- **"Drop AA / smart-account entirely; UserVault is a plain Solidity contract owned by the user's EOA."** Rejected — loses gasless UX for strategy operators (which Helios.md §3 leans on) and removes the spending-rules layer that makes the threat model defensible.
