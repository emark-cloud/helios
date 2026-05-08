/**
 * Sentinel WS event stream — single subscription, lifted out of
 * `ActivityRail` so multiple dashboard surfaces can read from it
 * without re-prompting the user for an EIP-191 signature.
 *
 * Surfaces:
 *   - `events`            — newest-first list (capped at 50)
 *   - `defundOf`          — `Map<strategyId, DefundRowState>` for table animation
 *   - `crossChainRepOf`   — per-strategy cross-chain reputation state:
 *                           pending GUIDs (drives `inFlight`) plus the
 *                           last resolved block number (drives
 *                           `pulseKey` so a 600ms pulse fires on a
 *                           genuinely new resolution).
 *   - `connState`         — open / connecting / error / closed
 *
 * Phase-5 / WS7: the cross-chain reputation source is wired through
 * `lib/crossChainWatcher.ts`, which subscribes to LayerZero
 * `ReputationMessageSent` events on Base/Arb and the matching
 * `ReputationMessageReceived` on Kite, then dispatches DOM events
 * we listen for here. The watcher silently no-ops when the
 * `NEXT_PUBLIC_HELIOS_OAPP_*` env addresses aren't populated, which
 * is the path exercised by Playwright's signature-interaction suite
 * (it drives the same DOM events directly via the `fireCrossChainRep*`
 * test helpers below).
 */

"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useSignMessage } from "wagmi";

import { startCrossChainWatcher } from "@/lib/crossChainWatcher";
import {
  subscribeUserEvents,
  type SentinelEvent,
  type SentinelEventKind,
} from "@/lib/sentinel";

const MAX_RAIL_ENTRIES = 50;

export type ConnState = "connecting" | "open" | "closed" | "error";

/** Per-strategy in-flight defund state. Maps to the row's
 *  `data-defund-state` attribute — globals.css colors the border. */
export type DefundRowState = "triggered" | "armed" | "finalizing" | "breaching" | "cancelled";

export type StreamRailEvent = SentinelEvent & { uid: string };

/** Per-strategy cross-chain reputation state. Decoupled from
 *  `repPulseOf` (the legacy single-timestamp shape) so the chain badge
 *  can render a sustained "in flight" dot during the LayerZero latency
 *  window without the pulse keyframe re-firing on every poll, and so
 *  it can pulse *only once* on the matching resolution. */
export type CrossChainRepState = {
  /** GUIDs of `ReputationMessageSent` emits on Base/Arb that have not
   *  yet been paired with a `ReputationMessageReceived` on Kite. */
  pendingGuids: ReadonlySet<string>;
  /** ms timestamp of the most recent resolution. */
  lastResolvedAt?: number;
  /** Kite-side block number that delivered the most recent resolution.
   *  Stable across re-renders, which is what `ChainBadge.pulseKey`
   *  needs to fire its keyframe exactly once per real arrival. */
  lastResolvedBlock?: string;
};

export type SentinelStream = {
  events: StreamRailEvent[];
  defundOf: ReadonlyMap<string, DefundRowState>;
  /** Cross-chain reputation pings keyed by strategy id. */
  crossChainRepOf: ReadonlyMap<string, CrossChainRepState>;
  connState: ConnState;
};

const noopStream: SentinelStream = {
  events: [],
  defundOf: new Map(),
  crossChainRepOf: new Map(),
  connState: "closed",
};

const StreamCtx = createContext<SentinelStream>(noopStream);

let _railUidCounter = 0;
function _mintUid(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  _railUidCounter += 1;
  return `stream-${Date.now()}-${_railUidCounter}`;
}

/** Synthesize a `SentinelEvent`-shaped row so the activity rail can
 *  render cross-chain rep updates through the same code path as the
 *  Sentinel-emitted rows. `tx_hash` is empty by design — the GUID
 *  isn't a transaction hash, and the rail's row component falls back
 *  cleanly when tx_hash is empty. */
function synthCrossChainEvent(
  kind: SentinelEventKind,
  strategyId: string,
  reason: string,
): SentinelEvent {
  return {
    user: "",
    kind,
    strategy: strategyId,
    amount_usd: 0,
    reason,
    timestamp: Math.floor(Date.now() / 1000),
    tx_hash: "",
  };
}

export function SentinelStreamProvider({
  user,
  children,
}: {
  user: string | undefined;
  children: ReactNode;
}): JSX.Element {
  const [events, setEvents] = useState<StreamRailEvent[]>([]);
  const [defundOf, setDefundOf] = useState<Map<string, DefundRowState>>(new Map());
  const [crossChainRepOf, setCrossChainRepOf] = useState<Map<string, CrossChainRepState>>(new Map());
  const [connState, setConnState] = useState<ConnState>(user ? "connecting" : "closed");
  const { signMessageAsync } = useSignMessage();

  const pushSynth = useCallback((evt: SentinelEvent) => {
    setEvents((prev) => {
      const next = [{ ...evt, uid: _mintUid() }, ...prev];
      return next.length > MAX_RAIL_ENTRIES ? next.slice(0, MAX_RAIL_ENTRIES) : next;
    });
  }, []);

  const handleEvent = useCallback((evt: SentinelEvent) => {
    setEvents((prev) => {
      const next = [{ ...evt, uid: _mintUid() }, ...prev];
      return next.length > MAX_RAIL_ENTRIES ? next.slice(0, MAX_RAIL_ENTRIES) : next;
    });
    const sid = evt.strategy?.toLowerCase() ?? null;
    const transition = defundTransitionFor(evt.kind);
    if (sid && transition !== undefined) {
      setDefundOf((prev) => {
        const next = new Map(prev);
        if (transition === null) next.delete(sid);
        else next.set(sid, transition);
        return next;
      });
    }
  }, []);

  // Phase-5 / WS7 — cross-chain reputation event bridge. The
  // `crossChainWatcher` module subscribes to viem `watchContractEvent`
  // for the LayerZero OApps and dispatches these DOM events; the
  // Playwright signature-interaction suite drives the same events
  // directly via `fireCrossChainRepInflight` / `fireCrossChainRepResolved`.
  useEffect(() => {
    if (typeof window === "undefined") return undefined;

    const onInflight = (e: Event): void => {
      const ce = e as CustomEvent<{ strategyId: string; guid: string; srcChainId?: number }>;
      const sid = ce.detail.strategyId.toLowerCase();
      const guid = ce.detail.guid.toLowerCase();
      setCrossChainRepOf((prev) => {
        const next = new Map(prev);
        const cur = next.get(sid) ?? { pendingGuids: new Set<string>() };
        const guids = new Set(cur.pendingGuids);
        if (guids.has(guid)) return prev; // idempotent — duplicate poll
        guids.add(guid);
        next.set(sid, { ...cur, pendingGuids: guids });
        return next;
      });
      pushSynth(
        synthCrossChainEvent(
          "CROSS_CHAIN_REP_UPDATE_INFLIGHT",
          sid,
          ce.detail.srcChainId ? `srcChain_${ce.detail.srcChainId}` : "",
        ),
      );
    };

    const onResolved = (e: Event): void => {
      const ce = e as CustomEvent<{ strategyId: string; guid: string; dstBlockNumber?: string }>;
      const sid = ce.detail.strategyId.toLowerCase();
      const guid = ce.detail.guid.toLowerCase();
      setCrossChainRepOf((prev) => {
        const next = new Map(prev);
        const cur = next.get(sid) ?? { pendingGuids: new Set<string>() };
        const guids = new Set(cur.pendingGuids);
        guids.delete(guid);
        next.set(sid, {
          pendingGuids: guids,
          lastResolvedAt: Date.now(),
          lastResolvedBlock: ce.detail.dstBlockNumber,
        });
        return next;
      });
      pushSynth(
        synthCrossChainEvent("CROSS_CHAIN_REP_UPDATE_RESOLVED", sid, ""),
      );
    };

    window.addEventListener("helios:cross-chain-rep-inflight", onInflight);
    window.addEventListener("helios:cross-chain-rep-resolved", onResolved);
    return () => {
      window.removeEventListener("helios:cross-chain-rep-inflight", onInflight);
      window.removeEventListener("helios:cross-chain-rep-resolved", onResolved);
    };
  }, [pushSynth]);

  // Boot the on-chain watcher exactly once for the provider's lifetime.
  // The watcher is keyed off env vars, not React state — gated to only
  // run when a user is connected so we don't burn RPC quota on the
  // unauthenticated landing page.
  useEffect(() => {
    if (!user) return undefined;
    const { teardown } = startCrossChainWatcher();
    return teardown;
  }, [user]);

  useEffect(() => {
    if (!user) {
      setConnState("closed");
      setEvents([]);
      setDefundOf(new Map());
      return undefined;
    }
    setConnState("connecting");
    setEvents([]);
    setDefundOf(new Map());
    let teardown: (() => void) | undefined;
    let cancelled = false;

    void (async () => {
      try {
        const unsub = await subscribeUserEvents(
          user,
          (digest) => signMessageAsync({ message: digest }),
          handleEvent,
          (status) => setConnState(status),
        );
        if (cancelled) {
          unsub();
        } else {
          teardown = unsub;
        }
      } catch {
        if (!cancelled) setConnState("error");
      }
    })();

    return () => {
      cancelled = true;
      teardown?.();
    };
  }, [user, signMessageAsync, handleEvent]);

  const value = useMemo<SentinelStream>(
    () => ({ events, defundOf, crossChainRepOf, connState }),
    [events, defundOf, crossChainRepOf, connState],
  );

  return <StreamCtx.Provider value={value}>{children}</StreamCtx.Provider>;
}

export function useSentinelStream(): SentinelStream {
  return useContext(StreamCtx);
}

/** Test-only escape hatch: simulate a cross-chain reputation update
 *  going in flight (Base/Arb `ReputationMessageSent`). The Playwright
 *  signature-interaction suite uses this to drive the chain badge
 *  in-flight dot without spinning up real LayerZero infrastructure.
 *  Pass a stable `guid` so the matching `fireCrossChainRepResolved`
 *  call clears the pending entry. */
export function fireCrossChainRepInflight(
  strategyId: string,
  guid: string,
  srcChainId: number = 84_532,
): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new CustomEvent("helios:cross-chain-rep-inflight", {
      detail: {
        strategyId: strategyId.toLowerCase(),
        guid: guid.toLowerCase(),
        srcChainId,
        srcBlockNumber: "0",
      },
    }),
  );
}

/** Test-only escape hatch: simulate the matching Kite-side
 *  `ReputationMessageReceived`. */
export function fireCrossChainRepResolved(
  strategyId: string,
  guid: string,
  dstBlockNumber: string = `${Date.now()}`,
): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new CustomEvent("helios:cross-chain-rep-resolved", {
      detail: {
        strategyId: strategyId.toLowerCase(),
        guid: guid.toLowerCase(),
        dstBlockNumber,
      },
    }),
  );
}

/** @deprecated Phase-4 fixture helper retained for back-compat with
 *  the existing Playwright test that simply wants to flash the pulse
 *  without orchestrating a paired GUID. Fires a synthetic inflight +
 *  immediate resolved against the same GUID. */
export function fireCrossChainRepPulse(strategyId: string): void {
  const guid = `0x${Date.now().toString(16).padStart(64, "0")}`;
  fireCrossChainRepInflight(strategyId, guid);
  // Microtask: keep the sequence ordered without forcing the consumer
  // to await a tick — the sentinel stream provider applies state
  // updates serially and the rail expects "inflight then resolved" in
  // that order.
  queueMicrotask(() => fireCrossChainRepResolved(strategyId, guid));
}

function defundTransitionFor(kind: SentinelEventKind): DefundRowState | null | undefined {
  switch (kind) {
    case "DEFUND_TRIGGERED":
      return "triggered";
    case "DEFUND_ARMED":
      return "armed";
    case "DEFUND_FINALIZED":
      return "finalizing";
    case "STRATEGY_DEFUNDED":
      return "breaching";
    case "DEFUND_CANCELLED":
      return null;
    default:
      return undefined;
  }
}
