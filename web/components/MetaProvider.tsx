"use client";

import { createContext, useContext, type ReactNode } from "react";

import type { Meta } from "@/lib/api";
import { useApi } from "@/lib/useApi";

export const TRUST_LINE = "Synthetic data. A flag is a prompt for a human to look, not a verdict.";

// Shown only until /api/meta arrives (or if it cannot be reached), so terms always have an explanation.
const FALLBACK_GLOSSARY: Record<string, string> = {
  overlap_score: "Overlap score: 0 to 100 points from five signals. A high score means a person should look.",
  band: "Band: the score grouped as Low, Medium or High.",
  cycling: "Cycling: a new loan taken within a few days of clearing a loan from another lender (borrowing to repay).",
  grace_period: "Grace period: days after the due date before a late repayment counts as late beyond grace.",
  labelled_abusive: "Labelled abusive: a model labelled the message a threat or shaming. Labels are a model's guesses.",
  confidence_interval: "Confidence interval: the range the true share probably lies in.",
  too_small: "Too small to rank: too few messages for its share to be compared.",
};

interface MetaContext {
  meta: Meta | undefined;
  glossary: Record<string, string>;
  trustLine: string;
}

const Context = createContext<MetaContext>({ meta: undefined, glossary: FALLBACK_GLOSSARY, trustLine: TRUST_LINE });

export function MetaProvider({ children }: { children: ReactNode }) {
  const { data } = useApi<Meta>("/api/meta");
  const value: MetaContext = {
    meta: data,
    glossary: { ...FALLBACK_GLOSSARY, ...(data?.glossary ?? {}) },
    trustLine: data?.trust_line ?? TRUST_LINE,
  };
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useMeta(): MetaContext {
  return useContext(Context);
}
