"use client";

// Restrained motion with the Motion library (Phase 14), built so that NO animation can hide or delay content:
//  - LazyMotion loads the DOM animation features ON DEMAND (motion-features.ts), so they are not part of the first
//    page's JavaScript; MotionConfig follows prefers-reduced-motion.
//  - Reveal fades and rises a section on first view, but only sections that start BELOW the fold after the page has
//    loaded. Anything already on screen (and everything before JavaScript runs) is shown at once.
// Number tiles count up with count-up.tsx; page changes fade in with a CSS animation (app/template.tsx).
import { LazyMotion, MotionConfig, useInView } from "motion/react";
import * as m from "motion/react-m";
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";

import { prefersReducedMotion } from "./count-up";

const useIsoLayoutEffect = typeof window === "undefined" ? useEffect : useLayoutEffect;

const loadFeatures = () => import("./motion-features").then((module) => module.default);

export function MotionProvider({ children }: { children: ReactNode }) {
  return (
    <LazyMotion features={loadFeatures} strict>
      <MotionConfig reducedMotion="user" transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}>
        {children}
      </MotionConfig>
    </LazyMotion>
  );
}

/** Fade and rise on first view, for sections that start below the fold. Never hides content that is already visible. */
export function Reveal({ children, className, delay = 0, as = "div" }: {
  children: ReactNode; className?: string; delay?: number; as?: "div" | "section" | "li";
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [armed, setArmed] = useState(false);
  const inView = useInView(ref, { once: true, margin: "0px 0px -10% 0px" });

  useIsoLayoutEffect(() => {
    const el = ref.current;
    if (!el || prefersReducedMotion()) return;
    if (el.getBoundingClientRect().top > window.innerHeight) setArmed(true); // below the fold: safe to animate
  }, []);

  const Component = m[as];
  return (
    <Component ref={ref as never} className={className}
      initial={false}
      animate={armed ? (inView ? { opacity: 1, y: 0 } : { opacity: 0, y: 18 }) : undefined}
      transition={{ delay: armed ? delay : 0 }}>
      {children}
    </Component>
  );
}

export { CountUp } from "./count-up";
export { m };
