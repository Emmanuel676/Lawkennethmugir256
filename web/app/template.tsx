"use client";

// Smooth page transitions (Phase 14). The first page a visitor opens is shown at once; later page changes fade and
// rise in over 0.2 s with a CSS animation (tw-animate-css), which prefers-reduced-motion switches off in globals.css.
// CSS rather than an animation library here, so no extra JavaScript sits in every page.
import { useEffect, type ReactNode } from "react";

let navigated = false;

export default function Template({ children }: { children: ReactNode }) {
  const animate = navigated;
  useEffect(() => {
    navigated = true;
  }, []);
  return <div className={animate ? "animate-in fade-in-0 slide-in-from-bottom-1 duration-200" : undefined}>{children}</div>;
}
