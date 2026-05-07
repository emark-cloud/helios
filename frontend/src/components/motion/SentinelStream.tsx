/**
 * Sentinel WS event stream — single subscription, lifted out of
 * `ActivityRail` so multiple dashboard surfaces can read from it
 * without re-prompting the user for an EIP-191 signature.
 *
 * Surfaces:
 *   - `events`     — newest-first list (capped at 50)
 *   - `defundOf`   — `Map<strategyId, DefundRowState>` for table animation
 *   - `repPulseOf` — `Map<strategyId, { firedAt: number }>` so a
 *                    chain badge can play one 600ms pulse on cross-chain
 *                    reputation arrival (DESIGN §10.3)
 *   - `connState`  — open / connecting / error / closed
 *
 * Phase 4 visual machinery only — the cross-chain reputation source is
 * a Phase 5 LayerZero deliverable per `docs/phase4-plan.md §4.9`.
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

export type SentinelStream = {
  events: StreamRailEvent[];
  defundOf: ReadonlyMap<string, DefundRowState>;
  /** Cross-chain reputation pings keyed by strategy id, with a
   *  `firedAt` ms timestamp so consumers can key animation restart. */
  repPulseOf: ReadonlyMap<string, { firedAt: number }>;
  connState: ConnState;
};

const noopStream: SentinelStream = {
  events: [],
  defundOf: new Map(),
  repPulseOf: new Map(),
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

export function SentinelStreamProvider({
  user,
  children,
}: {
  user: string | undefined;
  children: ReactNode;
}): JSX.Element {
  const [events, setEvents] = useState<StreamRailEvent[]>([]);
  const [defundOf, setDefundOf] = useState<Map<string, DefundRowState>>(new Map());
  const [repPulseOf, setRepPulseOf] = useState<Map<string, { firedAt: number }>>(new Map());
  const [connState, setConnState] = useState<ConnState>(user ? "connecting" : "closed");
  const { signMessageAsync } = useSignMessage();

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
    // Cross-chain reputation hook is dormant in Phase 4 — see plan
    // §4.9. Reserved kinds map here in Phase 5.
  }, []);

  // Phase-4 fixture bridge — see `fireCrossChainRepPulse` doc. Wired
  // here so the provider is the single source of truth for the
  // signature-moment animations.
  useEffect(() => {
    if (typeof window === "undefined") return undefined;
    const handler = (e: Event): void => {
      const ce = e as CustomEvent<{ strategyId: string; firedAt: number }>;
      setRepPulseOf((prev) => {
        const next = new Map(prev);
        next.set(ce.detail.strategyId, { firedAt: ce.detail.firedAt });
        return next;
      });
    };
    window.addEventListener("helios:rep-pulse", handler);
    return () => window.removeEventListener("helios:rep-pulse", handler);
  }, []);

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
    () => ({ events, defundOf, repPulseOf, connState }),
    [events, defundOf, repPulseOf, connState],
  );

  return <StreamCtx.Provider value={value}>{children}</StreamCtx.Provider>;
}

export function useSentinelStream(): SentinelStream {
  return useContext(StreamCtx);
}

/** Test-only escape hatch so signature-interaction Playwright tests
 *  can drive the cross-chain pulse without LayerZero. The shape mirrors
 *  the future Phase 5 reputation_updated event. */
export function fireCrossChainRepPulse(strategyId: string): void {
  const detail = { strategyId: strategyId.toLowerCase(), firedAt: Date.now() };
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent("helios:rep-pulse", { detail }));
  }
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
