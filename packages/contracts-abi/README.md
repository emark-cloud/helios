# @helios/contracts-abi

Shared contract ABIs + typed addresses. The **single source of truth** imported by services, subgraph, and frontend. ABI fragments are never duplicated elsewhere in the repo.

## How it works

1. `forge build` (in `contracts/`) writes artifacts to `contracts/out/`.
2. `pnpm --filter @helios/contracts-abi build` runs `scripts/generate.mjs`, which:
   - Reads each tracked contract's Foundry artifact
   - Emits `src/abis/<Name>.ts` with an `as const` ABI export (compatible with viem/wagmi)
   - Emits `../contracts-abi-py/src/helios_contracts_abi/abis.py` for Python services
3. TypeScript is compiled to `dist/` and exported via `@helios/contracts-abi`.

## When to regenerate

Any time a contract ABI changes — adding a function, adding/renaming an event, changing a struct.

```bash
cd contracts && forge build
cd ../packages/contracts-abi && pnpm build
# Downstream: commit & push so services, subgraph, frontend consume the updated ABI.
```

## Usage

### TypeScript / viem / wagmi

```ts
import { IUserVaultAbi, ADDRESSES } from "@helios/contracts-abi";
import { createPublicClient, http } from "viem";

const client = createPublicClient({ transport: http(process.env.KITE_RPC_URL!) });
const meta = await client.readContract({
  address: ADDRESSES["kite-testnet"].userVault!,
  abi: IUserVaultAbi,
  functionName: "metaStrategyOf",
  args: [userAddress],
});
```

### Python

```python
from helios_contracts_abi.abis import IUserVault_ABI
from web3 import Web3
w3 = Web3(Web3.HTTPProvider(os.environ["KITE_RPC_URL"]))
vault = w3.eth.contract(address=address, abi=IUserVault_ABI)
```
