// shadcn/ui Select (Radix), themed with the FairLend brand tokens. Opening animations come from tw-animate-css and
// are switched off by prefers-reduced-motion in globals.css.
"use client";

import * as SelectPrimitive from "@radix-ui/react-select";
import { Check, ChevronDown } from "lucide-react";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";
import { popover } from "./popover";

export const Select = SelectPrimitive.Root;
export const SelectValue = SelectPrimitive.Value;

export function SelectTrigger({ className, children, ...props }: ComponentProps<typeof SelectPrimitive.Trigger>) {
  return (
    <SelectPrimitive.Trigger
      className={cn("flex h-10 w-full min-w-0 items-center justify-between gap-2 rounded-lg border border-line bg-surface px-3 text-left text-sm text-ink " +
        "shadow-[inset_0_1px_1px_rgba(15,23,42,0.04)] outline-none focus-visible:border-accent focus-visible:ring-3 " +
        "focus-visible:ring-[color-mix(in_oklab,var(--accent)_25%,transparent)] data-[placeholder]:text-muted " +
        "disabled:opacity-50 [&>span]:truncate", className)} {...props}>
      {children}
      <SelectPrimitive.Icon asChild><ChevronDown className="size-4 shrink-0 text-muted" aria-hidden="true" /></SelectPrimitive.Icon>
    </SelectPrimitive.Trigger>
  );
}

export function SelectContent({ className, children, position = "popper", ...props }: ComponentProps<typeof SelectPrimitive.Content>) {
  return (
    <SelectPrimitive.Portal>
      <SelectPrimitive.Content position={position} sideOffset={6}
        className={cn(popover, "max-h-80 min-w-[var(--radix-select-trigger-width)] overflow-hidden", className)} {...props}>
        <SelectPrimitive.Viewport className="p-1.5">{children}</SelectPrimitive.Viewport>
      </SelectPrimitive.Content>
    </SelectPrimitive.Portal>
  );
}

export function SelectItem({ className, children, ...props }: ComponentProps<typeof SelectPrimitive.Item>) {
  return (
    <SelectPrimitive.Item
      className={cn("relative flex cursor-pointer select-none items-center rounded-lg py-2 pl-8 pr-2.5 text-sm text-ink-2 outline-none " +
        "data-[highlighted]:bg-surface-2 data-[highlighted]:text-ink data-[disabled]:opacity-50", className)} {...props}>
      <span className="absolute left-2.5 flex size-4 items-center justify-center">
        <SelectPrimitive.ItemIndicator><Check className="size-4 text-accent" aria-hidden="true" /></SelectPrimitive.ItemIndicator>
      </span>
      <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
    </SelectPrimitive.Item>
  );
}
