# Kite Passport / AA SDK — Operational notes

Operational reference for working against Kite Passport in Helios. Describes
the actual primitives shipped by Kite, not the v0-spec assumption. **Read
[`docs/kite-passport-integration.md`](kite-passport-integration.md) first** for the design proposal that
this doc operationalizes (Choices C + E + F → G).

Last spike: 2026-04-30 (SDK-tarball inspection, Kite docs).

## TL;DR

Kite ships **two** Passport surfaces, not one:

| Surface | Audience | Helios usage |
|---|---|---|
| `@gokite-network/auth` (npm, Particle-Network-backed) | **End-user frontends.** Passkey/email/social login → ERC-4337 smart account. | `/onboard` — provisions the user's AA wallet, the wallet then calls `UserVault.setMetaStrategy` etc. |
| `kpass` CLI + `gokite-aa-sdk` x402 client libs | **AI-agent flows.** Approved spending sessions → paid HTTP services via x402, settled by Pieverse. | Phase 2 demo polish (Choice G) — Allocator pays the prover/oracle/audit endpoints via x402. |

Both layered on the same primitive: an ERC-4337 smart account on Kite, owned by a Particle-MPC EOA, signed by passkey/email at the user's device. There is **no BIP-32 hierarchical session-key derivation** in the SDK — the v0 Helios spec assumed this; reality is plain ERC-4337 + paymaster, and Helios enforces the cascade in Solidity ACL.

## Versions (locked)

| Package | Version | Notes |
|---|---|---|
| `gokite-aa-sdk` | `1.0.15` | npm. Pin exact; the verifier-adapter ABIs and EntryPoint addresses bind to this. |
| `@gokite-network/auth` | `0.1.16` | npm. Particle-Network-backed; last published 2025-11-01. Pin exact; revisit during Phase 4. |
| Kite testnet | chain id `2368`, RPC `https://rpc-testnet.gokite.ai/`, explorer `https://testnet.kitescan.io/`, faucet `https://faucet.gokite.ai` | |
| Kite mainnet | chain id `2366`, RPC `https://rpc.gokite.ai/`, explorer `https://kitescan.ai/` | Live since 2026-04-28; Phase 6 promotion target. |
| Pieverse facilitator | `https://facilitator.pieverse.io`, scheme `gokite-aa` | x402 settlement. Phase 2 demo polish only. |
| Testnet USDC (x402 examples) | `0x0fF5393387ad2f9f691FD6Fd28e07E3969e27e63` | Used in Kite docs' x402 walkthrough. |

## SDK surface — `gokite-aa-sdk`

Thin ERC-4337 client over Kite's bundler + EntryPoint. Public surface (from
`dist/gokite-aa-sdk.d.ts` v1.0.15):

```ts
new GokiteAASDK(network, rpcUrl, bundlerUrl?)

// Account
sdk.getAccountAddress(owner, salt?)
sdk.getAccountNonce(accountAddress)
sdk.isAccountDeployed(accountAddress)
sdk.buildInitCode(owner, salt)

// Calls
sdk.buildCallData({ target, value?, callData })            // single
sdk.buildBatchCallData({ targets, values?, callDatas })    // batched

// User operations
sdk.createUserOperation(owner, request, salt?, paymasterAddress?, tokenAddress?)
sdk.estimateGas(userOp)
sdk.estimateUserOperation(owner, request)
  // returns { sponsorshipAvailable, remainingSponsorships, supportedTokens, paymasterAddress, userOp }
sdk.sendUserOperation(owner, request, signFn, salt?, paymasterAddress?, tokenAddress?)
sdk.sendUserOperationAndWait(owner, request, signFn, salt?, paymasterAddress?, pollingOptions?)
sdk.sendUserOperationWithPayment(owner, request, baseUserOp, tokenAddress, signFn, ...)
sdk.sendUserOperationDirectly(owner, userOp)               // bypasses bundler
sdk.pollUserOperationStatus(userOpHash, pollingOptions?)
sdk.getUserOperationStatus(userOpHash)
sdk.getUserOpHash(userOp)

// Re-export
DelegatorStakingClient                                     // staking helper
```

`SignFunction = (userOpHash: string) => Promise<string>` — flat signature
callback, no parent/child key derivation.

**Not in the SDK:** session-key delegation, EIP-1271 helpers, allowlist
configuration, BIP-32 child-key derivation. Spending rules referenced in the
docs page are contract-side rules on the agent wallet, not SDK methods.

## Widget surface — `@gokite-network/auth`

Frontend embedding for Passport login + smart-account binding. Built on
`@particle-network/auth` + `@particle-network/aa` + `@particle-network/provider`.

```ts
import GokiteNetwork, { SmartAccount, gokiteTestnet } from "@gokite-network/auth";

const sa = new SmartAccount(particleAuth, gokiteTestnet, {
  entryPointAddress: "0x...",
  smartAccountFactoryAddress: "0x...",
  secretKey: process.env.NEXT_PUBLIC_PARTICLE_CLIENT_KEY!,
});

const network = new GokiteNetwork(sa, particleAuth, signInRpc?);
await network.login({ /* passkey/email/social, see @particle-network/auth LoginOptions */ });
const aaAddress = await sa.getAddress();
```

The `GokiteNetwork.user` getter exposes the Particle `UserInfo`; `signin()`
returns `IdentifyState` with `aa_address`, `displayed_name`, `avatar_url`,
`access_token`, `eoa`. That `aa_address` is the user's UserVault owner.

## Helios integration patterns

### Pattern 1 — onboarding flow (`/onboard`)

Choice C from `kite-passport-integration.md`. Frontend-only; no service-side
Passport plumbing.

```ts
// 1. user logs in
await heliosNetwork.login({ /* passkey */ });
const owner = await sa.getAddress();              // user's AA wallet

// 2. build batched userOp: approve USDC + deposit + setMetaStrategy + delegateToAllocator
const calls = [
  { target: USDC_ADDR,        value: 0n, callData: encodeApprove(USER_VAULT, depositAmount) },
  { target: USER_VAULT,       value: 0n, callData: encodeDeposit(depositAmount) },
  { target: USER_VAULT,       value: 0n, callData: encodeSetMetaStrategy(metaStruct) },
  { target: USER_VAULT,       value: 0n, callData: encodeDelegateToAllocator(SENTINEL_EOA) },
];

// 3. estimate (paymaster gives sponsorship status)
const est = await sdk.estimateUserOperation(owner, { targets: calls.map(c=>c.target), values: calls.map(c=>c.value), callDatas: calls.map(c=>c.callData) });

// 4. send (paymaster-sponsored if est.sponsorshipAvailable, else pay gas in USDC via sendUserOperationWithPayment)
const { userOpHash, status } = await sdk.sendUserOperationAndWait(owner, request, signFn, undefined, est.paymasterAddress);
```

The `signFn` proxies the userOp hash to Particle for the user's passkey to
sign. **One passkey prompt** for the whole onboarding flow.

### Pattern 2 — Allocator/Strategy operator submissions

These are EOAs registered in `AllocatorRegistry` / `StrategyRegistry`. They
sign and broadcast plain transactions with `web3.py` / `viem`, the same way
as today. Passport is not on this path. Phase 2 demo polish (Choice G) layers
x402 on top — see Pattern 3.

### Pattern 3 — x402 paid services (Phase 2 / Choice G)

Allocator pays prover/oracle/audit per call. Service responds `402 Payment
Required` with terms; Allocator attaches `X-Payment` header drawn from an
active session; service validates via `POST facilitator.pieverse.io/v2/verify`
and settles via `/v2/settle`. Implementation is an x402-aware FastAPI
middleware on each service. Helios is then a *service provider* on Kite's
agent economy, not just a consumer.

The `kpass` CLI is the consumer-side reference implementation for an agent
that wants to call x402 services interactively. For Helios's Allocator
service we'll integrate the equivalent client lib directly into the Python
service rather than shelling out to `kpass`.

## Open questions (deferred to Phase 2 G workstream)

- **Pieverse mainnet/testnet endpoint split.** Is `facilitator.pieverse.io`
  the same endpoint for both, with `network` field disambiguating? Confirm
  before x402 integration lands.
- **Canonical mainnet USDC for Passport settlement.** Testnet `0x0fF5...e63`
  is a test token. Mainnet candidate `USDC.e` at
  `0x7aB6f3ed87C42eF0aDb67Ed95090f8bF5240149e` per
  `reference_kite_contract_surface` memory; confirm the facilitator settles
  in this contract (rather than a different bridged USDC).
- **Embeddable widget freshness.** `@gokite-network/auth@0.1.16` last
  published 2025-11-01. Re-validate compatibility with Particle Network
  upstream changes before Phase 4 onboarding rebuild.

## Threat model implications (vs v0 spec)

The v0 Helios spec promised "BIP-32 hierarchical, root keys never leave the
enclave." Reality:

- The "root key" is an MPC share held by Particle Network. **Not** hardware-held.
- Cascade authority (Allocator → Strategy) is enforced in **Solidity ACL**, not in identity-derivation.
- Compromising Particle MPC + a user's email + passkey lets an attacker drain. This is the same threat model as Privy / Magic / Web3Auth — documented honestly in `Helios.md §15`.
- Compromising the Allocator's EOA key is bounded to the meta-strategy in `AllocatorVault` — Solidity reverts any out-of-bounds allocation. The user revokes by calling `delegateToAllocator(address(0))`.

The "non-custodial" claim survives in the sense that Particle doesn't have
unilateral access to user funds (MPC), but the trust footprint is strictly
larger than "hardware EOA." We say so plainly in §15.1.

## Migration plan from Phase 1 stubs

Phase 1 frontend tagged every Passport touchpoint with `[PASSPORT-STUB]` and
used EOA `personal_sign` against MetaMask. Phase 4 onboarding rewrite:

1. Add `@gokite-network/auth@0.1.16` and `gokite-aa-sdk@1.0.15` to
   `frontend/package.json` (pin exact).
2. Replace `OnboardClient.tsx` wallet connect + `personal_sign` flow with
   `GokiteNetwork.login()` + `SmartAccount.getAddress()`.
3. Replace the EOA tx submission for `setMetaStrategy` with the
   batched-userOp pattern from §"Pattern 1" above.
4. Drop the `[PASSPORT-STUB]` comment tags as each touchpoint migrates.
5. Update `.env.example`: rename `KITE_PASSPORT_SIGNER_PK` →
   `NEXT_PUBLIC_PARTICLE_PROJECT_ID` + `NEXT_PUBLIC_PARTICLE_CLIENT_KEY` +
   `NEXT_PUBLIC_PARTICLE_APP_ID`. Add `NEXT_PUBLIC_AA_ENTRYPOINT_ADDRESS` and
   `NEXT_PUBLIC_AA_FACTORY_ADDRESS` (pull from Kite docs once published).
6. Re-record demo voiceover (`Helios.md §14.1`) — passkey, no MetaMask popup.
7. Re-run `scripts/e2e-scenario.sh` against the new flow; confirm Phase 1
   acceptance criteria still hold.

Tracked as concrete items in `TODO.md` Phase 4 section.
