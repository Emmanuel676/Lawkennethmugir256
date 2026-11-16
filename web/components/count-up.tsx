"use client";

// Number tiles count up once, in 0.7 s, after their value has arrived (Phase 14). Plain React and
// requestAnimationFrame, so the shared page kit does not pull an animation library into every page.
// prefers-reduced-motion shows the value directly; screen readers always get the final value.
import { useEffect, useRef, useState } from "react";

export function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && Boolean(window.matchMedia?.("(prefers-reduced-motion: reduce)").matches);
}

/** Animates the first number inside `value` from 0 (keeping its prefix, suffix, separators and decimals), once. */
export function CountUp({ value }: { value: string }) {
  const [shown, setShown] = useState(value);
  const done = useRef(false);

  useEffect(() => {
    const match = /^(.*?)(\d[\d,]*(?:\.\d+)?)(.*)$/.exec(value);
    if (done.current || !match || prefersReducedMotion()) {
      setShown(value);
      return;
    }
    done.current = true;
    const [, prefix, number, suffix] = match;
    const target = Number(number.replace(/,/g, ""));
    const decimals = number.includes(".") ? number.split(".")[1].length : 0;
    const grouped = number.includes(",");
    const format = (n: number) => grouped
      ? n.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
      : n.toFixed(decimals);
    const start = performance.now();
    let frame = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / 700);
      const eased = 1 - Math.pow(1 - t, 3);
      setShown(`${prefix}${format(target * eased)}${suffix}`);
      if (t < 1) frame = requestAnimationFrame(tick);
      else setShown(value);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value]);

  return (
    <>
      <span aria-hidden="true">{shown}</span>
      <span className="sr-only">{value}</span>
    </>
  );
}
