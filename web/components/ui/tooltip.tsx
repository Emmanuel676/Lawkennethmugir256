// shadcn/ui Tooltip (Radix), themed with the FairLend brand tokens. Opening animations come from tw-animate-css and
// are switched off by prefers-reduced-motion in globals.css.
"use client";

import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";
import { popover } from "./popover";

export const TooltipProvider = TooltipPrimitive.Provider;
export const Tooltip = TooltipPrimitive.Root;
export const TooltipTrigger = TooltipPrimitive.Trigger;

export function TooltipContent({ className, sideOffset = 6, children, ...props }: ComponentProps<typeof TooltipPrimitive.Content>) {
  return (
    <TooltipPrimitive.Portal>
      <TooltipPrimitive.Content sideOffset={sideOffset}
        className={cn(popover, "max-w-72 px-3 py-2.5 text-[13px] leading-snug text-ink-2", className)} {...props}>
        {children}
        <TooltipPrimitive.Arrow className="fill-[var(--surface)]" />
      </TooltipPrimitive.Content>
    </TooltipPrimitive.Portal>
  );
}
