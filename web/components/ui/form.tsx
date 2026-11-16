// shadcn/ui Input, Textarea, Label and Checkbox, themed with the FairLend brand tokens.
"use client";

import * as CheckboxPrimitive from "@radix-ui/react-checkbox";
import * as LabelPrimitive from "@radix-ui/react-label";
import { Check } from "lucide-react";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

const field =
  "w-full min-w-0 rounded-lg border border-line bg-surface px-3 text-sm text-ink shadow-[inset_0_1px_1px_rgba(15,23,42,0.04)] " +
  "placeholder:text-muted outline-none transition-[border-color,box-shadow] focus-visible:border-accent " +
  "focus-visible:ring-3 focus-visible:ring-[color-mix(in_oklab,var(--accent)_25%,transparent)] " +
  "aria-invalid:border-[#e11d48] disabled:cursor-not-allowed disabled:opacity-50";

export function Input({ className, type, ...props }: ComponentProps<"input">) {
  return <input type={type} data-slot="input" className={cn(field, "h-10 py-2", className)} {...props} />;
}

export function Textarea({ className, ...props }: ComponentProps<"textarea">) {
  return <textarea data-slot="textarea" className={cn(field, "min-h-24 py-2.5 leading-relaxed", className)} {...props} />;
}

export function Label({ className, ...props }: ComponentProps<typeof LabelPrimitive.Root>) {
  return <LabelPrimitive.Root data-slot="label" className={cn("text-sm font-medium text-ink-2 select-none", className)} {...props} />;
}

export function Checkbox({ className, ...props }: ComponentProps<typeof CheckboxPrimitive.Root>) {
  return (
    <CheckboxPrimitive.Root data-slot="checkbox"
      className={cn("peer grid size-[18px] shrink-0 place-items-center rounded-[5px] border border-line bg-surface " +
        "shadow-[inset_0_1px_1px_rgba(15,23,42,0.05)] outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)] " +
        "focus-visible:ring-offset-2 data-[state=checked]:border-accent data-[state=checked]:bg-accent " +
        "data-[state=checked]:text-accent-ink disabled:opacity-50", className)} {...props}>
      <CheckboxPrimitive.Indicator><Check className="size-3.5" strokeWidth={3} aria-hidden="true" /></CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  );
}
