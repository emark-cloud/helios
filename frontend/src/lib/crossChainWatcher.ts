/**
 * Phase 5 / WS7 — cross-chain reputation watcher.
 *
 * Listens for LayerZero-mediated reputation messages on the three
 * supported chains and dispatches DOM events that
 * `SentinelStreamProvider` consumes:
 *
 * - `ReputationMessageSent(dstEid, actor, actorType, guid)` on Base /
 *   Arbitrum Sepolia → `helios:cross-chain-rep-inflight`.
 * - `ReputationMessageReceived(srcEid, actor, actorType, guid)` on
 *   Kite testnet → `helios:cross-chain-rep-resolved` (paired by GUID).
 *
 * Wired here rather than inside the Sentinel WS for two reasons: the
 * dashboard already has the wagmi/viem stack loaded so we don't add a
 * new dependency edge, and the messages are produced by `HeliosOApp`
 * whose address rotates on every redeploy — keeping the source close
 * to the consumer means the env wiring lives next to the rest of the
 * frontend chain config.
 *
 * No-ops gracefully when any of the three OApp addresses or RPC URLs
 * are missing; this is the path exercised in CI and during the
 * pre-WS2-broadcast window. The Playwright signature-interaction
 * suite drives the same DOM events directly via `fireCrossChainRep*`.
 */

import {
  createPublicClient,
  http,
  type Address,
  type Hex,
  type PublicClient,
} from "viem";
import { arbitrumSepolia, baseSepolia } from "viem/chains";

import { kiteTestnet } from "@/lib/chains";

/** Subset of `IHeliosOApp` events we care about on the frontend. The
 *  full ABI lives in `@helios/contracts-abi`; we re-declare just the
 *  two events because viem's `watchContractEvent` only needs the event
 *  fragment and the smaller surface keeps the bundle lean. */
const HELIOS_OAPP_EVENT_ABI = [
  {
    type: "event",
    name: "ReputationMessageSent",
    inputs: [
      { name: "dstEid", type: "uint32", indexed: true },
      { name: "actor", type: "address", indexed: true },
      { name: "actorType", type: "uint8", indexed: false },
      { name: "guid", type: "bytes32", indexed: false },
    ],
    anonymous: false,
  },
  {
    type: "event",
    name: "ReputationMessageReceived",
    inputs: [
      { name: "srcEid", type: "uint32", indexed: true },
      { name: "actor", type: "address", indexed: true },
      { name: "actorType", type: "uint8", indexed: false },
      { name: "guid", type: "bytes32", indexed: false },
    ],
    anonymous: false,
  },
] as const;

export type CrossChainRepInflightDetail = {
  /** Lower-cased actor address — matches the keying convention used by
   *  the Sentinel stream's strategy maps. */
  strategyId: string;
  /** LayerZero message GUID, hex-encoded. Used to pair the resolved
   *  event back to the inflight one. */
  guid: string;
  /** Source chain id (where `ReputationMessageSent` fired). */
  srcChainId: number;
  /** Block number of the source-chain emit, as a string so the detail
   *  is JSON-clonable across worker boundaries. */
  srcBlockNumber: string;
};

export type CrossChainRepResolvedDetail = {
  strategyId: string;
  guid: string;
  /** Block number of the Kite-side `ReputationMessageReceived` emit. */
  dstBlockNumber: string;
};

const env = (k: string): string | undefined => {
  const v = process.env[k];
  return v && v.length > 0 ? v : undefined;
};

const KITE_OAPP = env("NEXT_PUBLIC_HELIOS_OAPP_KITE") as Address | undefined;
const BASE_OAPP = env("NEXT_PUBLIC_HELIOS_OAPP_BASE") as Address | undefined;
const ARB_OAPP = env("NEXT_PUBLIC_HELIOS_OAPP_ARB") as Address | undefined;

const KITE_RPC = env("NEXT_PUBLIC_KITE_RPC_URL") ?? kiteTestnet.rpcUrls.default.http[0];
const BASE_RPC = env("NEXT_PUBLIC_BASE_SEPOLIA_RPC_URL");
const ARB_RPC = env("NEXT_PUBLIC_ARBITRUM_SEPOLIA_RPC_URL");

function makeClient(chain: typeof kiteTestnet | typeof baseSepolia | typeof arbitrumSepolia, rpc: string | undefined): PublicClient | null {
  // viem chains carry a default RPC; we override when the env supplies
  // one so testnet work can route through a private endpoint without
  // touching the chain definition.
  const transport = http(rpc);
  return createPublicClient({ chain, transport }) as PublicClient;
}

function dispatchInflight(detail: CrossChainRepInflightDetail): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new CustomEvent<CrossChainRepInflightDetail>("helios:cross-chain-rep-inflight", { detail }),
  );
}

function dispatchResolved(detail: CrossChainRepResolvedDetail): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new CustomEvent<CrossChainRepResolvedDetail>("helios:cross-chain-rep-resolved", { detail }),
  );
}

type Teardown = () => void;

/**
 * Boot the cross-chain watcher. Returns a teardown that removes every
 * subscription. Safe to call multiple times — each call returns its
 * own teardown, but in practice the SentinelStreamProvider mounts a
 * single watcher tied to its lifecycle.
 *
 * When any of the three OApp addresses / RPCs are missing, the watcher
 * skips that leg silently (and logs once at debug level via the
 * returned diagnostics object). The Playwright fixture path remains
 * usable regardless.
 */
export function startCrossChainWatcher(): { teardown: Teardown; watching: { kite: boolean; base: boolean; arbitrum: boolean } } {
  const teardowns: Teardown[] = [];
  const watching = { kite: false, base: false, arbitrum: false };

  const watchSent = (client: PublicClient | null, address: Address | undefined, srcChainId: number): void => {
    if (!client || !address) return;
    const unwatch = client.watchContractEvent({
      address,
      abi: HELIOS_OAPP_EVENT_ABI,
      eventName: "ReputationMessageSent",
      onLogs: (logs) => {
        for (const log of logs) {
          const args = log.args as { actor?: Address; guid?: Hex };
          if (!args.actor || !args.guid) continue;
          dispatchInflight({
            strategyId: args.actor.toLowerCase(),
            guid: args.guid.toLowerCase(),
            srcChainId,
            srcBlockNumber: log.blockNumber != null ? log.blockNumber.toString() : "0",
          });
        }
      },
      // viem will fall back to log polling when the transport doesn't
      // support filters (the default for plain http). Polling cadence
      // matches the Sentinel WS rebalance heartbeat so the rail and
      // chain badge feel consistent.
      pollingInterval: 4_000,
    });
    teardowns.push(unwatch);
  };

  const watchReceived = (client: PublicClient | null, address: Address | undefined): void => {
    if (!client || !address) return;
    const unwatch = client.watchContractEvent({
      address,
      abi: HELIOS_OAPP_EVENT_ABI,
      eventName: "ReputationMessageReceived",
      onLogs: (logs) => {
        for (const log of logs) {
          const args = log.args as { actor?: Address; guid?: Hex };
          if (!args.actor || !args.guid) continue;
          dispatchResolved({
            strategyId: args.actor.toLowerCase(),
            guid: args.guid.toLowerCase(),
            dstBlockNumber: log.blockNumber != null ? log.blockNumber.toString() : "0",
          });
        }
      },
      pollingInterval: 4_000,
    });
    teardowns.push(unwatch);
  };

  if (KITE_OAPP) {
    const client = makeClient(kiteTestnet, KITE_RPC);
    watchReceived(client, KITE_OAPP);
    watching.kite = true;
  }
  if (BASE_OAPP && BASE_RPC) {
    const client = makeClient(baseSepolia, BASE_RPC);
    watchSent(client, BASE_OAPP, baseSepolia.id);
    watching.base = true;
  }
  if (ARB_OAPP && ARB_RPC) {
    const client = makeClient(arbitrumSepolia, ARB_RPC);
    watchSent(client, ARB_OAPP, arbitrumSepolia.id);
    watching.arbitrum = true;
  }

  const teardown: Teardown = () => {
    for (const t of teardowns) {
      try {
        t();
      } catch {
        // viem's unwatch is idempotent in practice but the harness
        // throws if the underlying transport already closed — swallow
        // so React 18's strict-mode double-mount doesn't crash.
      }
    }
  };
  return { teardown, watching };
}
