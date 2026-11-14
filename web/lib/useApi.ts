"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { getJson, type Params } from "./api";

export interface ApiState<T> {
  data: T | undefined;
  error: string | undefined;
  loading: boolean;
  reload: () => void;
}

/** Fetch one endpoint; refetches when the path or params change. Keeps the last data while a new page loads. */
export function useApi<T>(path: string | null, params?: Params): ApiState<T> {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const key = path === null ? null : `${path}?${JSON.stringify(params ?? {})}`;
  const paramsRef = useRef(params);
  paramsRef.current = params;

  useEffect(() => {
    if (key === null || path === null) return;
    const controller = new AbortController();
    setLoading(true);
    setError(undefined);
    getJson<T>(path, paramsRef.current, controller.signal)
      .then((body) => {
        setData(body);
        setLoading(false);
      })
      .catch((err: Error) => {
        if (err.name === "AbortError") return;
        setError(err.message);
        setLoading(false);
      });
    return () => controller.abort();
  }, [key, path, tick]);

  const reload = useCallback(() => setTick((n) => n + 1), []);
  return { data, error, loading, reload };
}
