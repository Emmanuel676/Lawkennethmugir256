// shadcn/ui Dropdown menu (Radix), themed with the FairLend brand tokens. Opening animations come from tw-animate-css and
// are switched off by prefers-reduced-motion in globals.css.
"use client";

import * as DropdownPrimitive from "@radix-ui/react-dropdown-menu";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";
import { popover } from "./popover";

export const DropdownMenu = DropdownPrimitive.Root;
export const DropdownMenuTrigger = DropdownPrimitive.Trigger;

export function DropdownMenuContent({ className, sideOffset = 6, ...props }: ComponentProps<typeof DropdownPrimitive.Content>) {
  return (
    <DropdownPrimitive.Portal>
      <DropdownPrimitive.Content sideOffset={sideOffset} className={cn(popover, "min-w-56 p-1.5", className)} {...props} />
    </DropdownPrimitive.Portal>
  );
}

export function DropdownMenuItem({ className, ...props }: ComponentProps<typeof DropdownPrimitive.Item>) {
  return (
    <DropdownPrimitive.Item
      className={cn("flex cursor-pointer select-none items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-ink-2 outline-none " +
        "data-[highlighted]:bg-surface-2 data-[highlighted]:text-ink [&_svg]:size-4", className)} {...props} />
  );
}

export function DropdownMenuLabel({ className, ...props }: ComponentProps<typeof DropdownPrimitive.Label>) {
  return <DropdownPrimitive.Label className={cn("px-2.5 py-2 text-xs text-muted", className)} {...props} />;
}

export function DropdownMenuSeparator({ className, ...props }: ComponentProps<typeof DropdownPrimitive.Separator>) {
  return <DropdownPrimitive.Separator className={cn("-mx-1.5 my-1 h-px bg-line", className)} {...props} />;
}
