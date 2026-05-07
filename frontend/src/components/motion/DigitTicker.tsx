/**
 * DigitTicker — animates a numeric value from prev to next via
 * digit-stepping at `--tick-step` cadence (30ms per step). DESIGN.md
 * §13: the auto-defund moment ticks the capital column down to zero
 * over ~2 seconds, one digit at a time, in monospace.
 *
 * Pure CSS would need keyframes per digit — instead we run a small
 * setTimeout cadence in JS, snapping `display` between the start and
 * end values across `steps` ticks. Reduced motion drops `steps` to
 * one so the value lands instantly.
 */

"use client";

import { useEffect, useRef, useState } from "react";

import { Numeric, type NumericTone } from "@/components/atoms/Numeric";

export type DigitTickerProps = {
  value: number;
  format: (_n: number) => string;
  /** Total ticks between previous and current value. */
  steps?: number;
  tone?: NumericTone;
  align?: "left" | "right";
  className?: string;
};

const PER_TICK_MS = 30;

export function DigitTicker({
  value,
  format,
  steps = 24,
  tone,
  align,
  className,
}: DigitTickerProps): JSX.Element {
  const [display, setDisplay] = useState(value);
  const prevRef = useRef(value);

  useEffect(() => {
    const start = prevRef.current;
    const end = value;
    if (start === end) {
      setDisplay(end);
      return undefined;
    }
    if (typeof window === "undefined") {
      setDisplay(end);
      prevRef.current = end;
      return undefined;
    }
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const totalSteps = reduce ? 1 : Math.max(1, steps);
    let i = 0;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const tick = (): void => {
      i += 1;
      const t = i / totalSteps;
      const next = start + (end - start) * t;
      setDisplay(i >= totalSteps ? end : next);
      if (i < totalSteps) {
        timer = setTimeout(tick, PER_TICK_MS);
      } else {
        prevRef.current = end;
      }
    };
    timer = setTimeout(tick, PER_TICK_MS);
    return () => {
      if (timer) clearTimeout(timer);
      prevRef.current = end;
    };
  }, [value, steps]);

  return (
    <Numeric tone={tone} align={align} className={className}>
      {format(display)}
    </Numeric>
  );
}
