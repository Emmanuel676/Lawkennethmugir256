"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import {
  getJson, ROLE_RANK, sendJson, type DatasetEntry, type DatasetList, type Me, type Params, type Role, type User,
} from "@/lib/api";
import { useApi, type ApiState } from "@/lib/useApi";

export const DEMO = "demo";
const DATASET_KEY = "fairlend-dataset";

interface SessionContext {
  ready: boolean;                       // the first /api/auth/me has answered
  user: User | null;
  can: (role: Role) => boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  refresh: () => Promise<void>;
  dataset: string;                      // slug the data pages show; the demo by default
  setDataset: (slug: string) => void;
  datasets: DatasetEntry[];             // the shared list (signed in), or just the demo
  reloadDatasets: () => void;
}

const DEMO_ENTRY: DatasetEntry = {
  slug: DEMO, name: "Demonstration data (built in)", kind: "demo", label: "Demonstration data. Built in; cannot be changed or deleted.", notes: "", source: "",
  added_by: "built in", added_at: null, updated_at: null, as_of_date: "", counts: {}, imports: 0, deletable: false,
};

const Context = createContext<SessionContext | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [user, setUser] = useState<User | null>(null);
  const [dataset, setDatasetState] = useState(DEMO);
  const [datasets, setDatasets] = useState<DatasetEntry[]>([DEMO_ENTRY]);
  const [listed, setListed] = useState(false);   // the shared list has arrived for the current user
  const [tick, setTick] = useState(0);

  const refresh = useCallback(async () => {
    try {
      const me = await getJson<Me>("/api/auth/me");
      setUser(me.user);
    } catch {
      setUser(null);
    } finally {
      setReady(true);
    }
  }, []);

  useEffect(() => {
    void refresh();
    try {
      const saved = localStorage.getItem(DATASET_KEY);
      if (saved) setDatasetState(saved);
    } catch {
      /* private mode: the demo it is */
    }
  }, [refresh]);

  // The shared dataset list, whenever the signed-in user changes (or after an import or a delete).
  useEffect(() => {
    if (!ready) return;
    setListed(false);
    if (!user) {
      setDatasets([DEMO_ENTRY]);
      return;
    }
    getJson<DatasetList>("/api/datasets")
      .then((body) => { setDatasets(body.datasets); setListed(true); })
      .catch(() => setDatasets([DEMO_ENTRY]));
  }, [ready, user, tick]);

  // A dataset that is gone (deleted, or not visible when signed out) falls back to the demo.
  useEffect(() => {
    if (!ready) return;
    if (dataset !== DEMO && (!user || (listed && !datasets.some((d) => d.slug === dataset)))) {
      setDatasetState(DEMO);
    }
  }, [ready, user, datasets, dataset, listed]);

  const setDataset = useCallback((slug: string) => {
    setDatasetState(slug);
    try {
      localStorage.setItem(DATASET_KEY, slug);
    } catch {
      /* not remembered */
    }
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    const me = await sendJson<Me>("POST", "/api/auth/login", { email, password });
    setUser(me.user);
  }, []);

  const signOut = useCallback(async () => {
    try {
      await sendJson<Me>("POST", "/api/auth/logout");
    } finally {
      setUser(null);
      setDataset(DEMO);
    }
  }, [setDataset]);

  const value = useMemo<SessionContext>(() => ({
    ready, user, refresh, signIn, signOut, dataset: ready && !user ? DEMO : dataset, setDataset, datasets,
    can: (role: Role) => Boolean(user && !user.disabled && ROLE_RANK[user.role] >= ROLE_RANK[role]),
    reloadDatasets: () => setTick((n) => n + 1),
  }), [ready, user, refresh, signIn, signOut, dataset, setDataset, datasets]);

  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useSession(): SessionContext {
  const context = useContext(Context);
  if (!context) throw new Error("useSession must be used inside SessionProvider");
  return context;
}

/** useApi for the data pages: adds the chosen dataset, and waits until we know who is signed in. */
export function useDatasetApi<T>(path: string, params?: Params): ApiState<T> {
  const { ready, dataset } = useSession();
  return useApi<T>(ready ? path : null, { ...(params ?? {}), dataset: dataset === DEMO ? undefined : dataset });
}

export function useCurrentDataset(): DatasetEntry {
  const { dataset, datasets } = useSession();
  return datasets.find((d) => d.slug === dataset) ?? DEMO_ENTRY;
}
