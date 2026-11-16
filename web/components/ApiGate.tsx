"use client";

// The "waking up" state (Phase 14). Free hosts put the API to sleep after a quiet spell, and the first visit can take
// about a minute. The page renders at once; if /api/health has not answered "ok" within a few seconds (or a data call
// later finds the service unreachable), a friendly full-page message replaces it and retries on its own. When the
// API is ready the page reloads, so every panel fetches fresh data. No raw error screens.
import { Coffee, Loader2 } from "lucide-react";
import Image from "next/image";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { API_DOWN_EVENT, API_BASE } from "@/lib/api";

const FIRST_WAIT_MS = 3500;
const RETRY_EVERY_MS = 4000;
const TRY_TIMEOUT_MS = 8000;

async function healthy(timeoutMs: number): Promise<boolean> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${API_BASE}/api/health`, { signal: controller.signal, cache: "no-store" });
    if (!response.ok) return false;
    const body = await response.json();
    return body?.status === "ok";
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

export function WakingUp({ attempts }: { attempts: number }) {
  return (
    <div role="status" aria-live="polite" className="hero-grid fixed inset-0 z-[60] grid place-items-center bg-bg px-6">
      <div className="max-w-md text-center">
        <Image src="/logo.svg" alt="FairLend Watch" width={230} height={62} className="mx-auto h-auto w-56" priority />
        <span className="mx-auto mt-8 grid size-14 place-items-center rounded-full bg-accent-soft text-accent">
          <Coffee className="size-7" aria-hidden="true" />
        </span>
        <h1 className="mt-5 text-2xl font-semibold tracking-tight text-ink">The service is waking up</h1>
        <p className="mt-2 text-[15px] leading-relaxed text-muted">
          It runs on a free host that sleeps when nobody is using it. Starting again can take about a minute.
          This page checks by itself and opens as soon as it is ready.
        </p>
        <p className="mt-6 inline-flex items-center gap-2 text-sm text-ink-2">
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
          Checking{attempts > 1 ? ` (try ${attempts})` : ""}…
        </p>
        <p className="mt-6 text-xs text-muted">Demonstration data. A flag is a prompt for a human to look, not a verdict.</p>
      </div>
    </div>
  );
}

export function ApiGate({ children }: { children: ReactNode }) {
  const [waking, setWaking] = useState(false);
  const [attempts, setAttempts] = useState(0);
  const polling = useRef(false);

  const poll = useCallback(async () => {
    if (polling.current) return;
    polling.current = true;
    setWaking(true);
    let n = 0;
    for (;;) {
      n += 1;
      setAttempts(n);
      if (await healthy(TRY_TIMEOUT_MS)) {
        window.location.reload();
        return;
      }
      await new Promise((r) => setTimeout(r, RETRY_EVERY_MS));
    }
  }, []);

  useEffect(() => {
    let settled = false;
    const firstWait = setTimeout(() => { if (!settled) void poll(); }, FIRST_WAIT_MS);
    healthy(FIRST_WAIT_MS + 500).then((ok) => {
      settled = true;
      clearTimeout(firstWait);
      if (!ok) void poll();
    });
    const onDown = () => { void (async () => { if (!(await healthy(FIRST_WAIT_MS))) void poll(); })(); };
    window.addEventListener(API_DOWN_EVENT, onDown);
    return () => {
      clearTimeout(firstWait);
      window.removeEventListener(API_DOWN_EVENT, onDown);
    };
  }, [poll]);

  return (
    <>
      {waking ? <WakingUp attempts={attempts} /> : null}
      <div aria-hidden={waking || undefined} className={waking ? "invisible" : undefined}>{children}</div>
    </>
  );
}
