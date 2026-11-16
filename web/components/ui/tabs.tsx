// shadcn/ui Tabs (Radix), themed with the FairLend brand tokens. Opening animations come from tw-animate-css and
// are switched off by prefers-reduced-motion in globals.css.
"use client";

import * as TabsPrimitive from "@radix-ui/react-tabs";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

export const Tabs = TabsPrimitive.Root;

export function TabsList({ className, ...props }: ComponentProps<typeof TabsPrimitive.List>) {
  return <TabsPrimitive.List className={cn("inline-flex items-center gap-1 rounded-xl bg-surface-2 p-1", className)} {...props} />;
}

export function TabsTrigger({ className, ...props }: ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      className={cn("inline-flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-sm font-medium text-muted outline-none transition-colors " +
        "hover:text-ink focus-visible:ring-2 focus-visible:ring-[var(--focus)] data-[state=active]:bg-surface data-[state=active]:text-ink " +
        "data-[state=active]:shadow-[0_1px_3px_rgba(15,23,42,0.1)]", className)} {...props} />
  );
}

export const TabsContent = TabsPrimitive.Content;
