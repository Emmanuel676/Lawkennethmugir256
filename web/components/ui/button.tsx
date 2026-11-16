// shadcn/ui Button, themed with the FairLend brand tokens (globals.css).
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

export const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-lg text-sm font-medium " +
  "transition-[background-color,box-shadow,color,opacity] outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)] " +
  "focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--surface)] disabled:pointer-events-none disabled:opacity-45 " +
  "[&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "bg-accent text-accent-ink shadow-[0_1px_2px_rgba(15,23,42,0.12),0_4px_12px_-4px_rgba(15,118,110,0.45)] hover:opacity-92",
        outline: "border border-line bg-surface text-ink-2 shadow-[0_1px_2px_rgba(15,23,42,0.05)] hover:bg-surface-2 hover:text-ink",
        ghost: "text-ink-2 hover:bg-surface-2 hover:text-ink",
        secondary: "bg-accent-soft text-accent hover:opacity-90",
        destructive: "bg-[#9f1239] text-white shadow-[0_1px_2px_rgba(15,23,42,0.12)] hover:bg-[#881337]",
        "destructive-outline": "border border-[#fda4af] text-[#9f1239] hover:bg-[#fff1f2] dark:border-[#9f1239] dark:text-[#fecdd3] dark:hover:bg-[#2a0a12]",
        link: "px-0 text-accent underline-offset-4 hover:underline",
      },
      size: {
        default: "h-10 px-4",
        sm: "h-8 rounded-md px-3 text-[13px]",
        lg: "h-12 rounded-xl px-6 text-[15px]",
        icon: "size-9",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export function Button({ className, variant, size, asChild = false, ...props }:
  ComponentProps<"button"> & VariantProps<typeof buttonVariants> & { asChild?: boolean }) {
  const Component = asChild ? Slot : "button";
  return <Component data-slot="button" className={cn(buttonVariants({ variant, size, className }))} {...props} />;
}
