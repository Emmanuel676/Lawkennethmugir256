"use client";

// The toast area is loaded after the page has rendered (Phase 14), so the toast library is not in the first page's
// JavaScript. Pages that show a toast import it themselves.
import dynamic from "next/dynamic";

export const LazyToaster = dynamic(() => import("./sonner").then((m) => m.Toaster), { ssr: false });
