// shadcn/ui Table primitives, themed with the FairLend brand tokens.
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

export function Table({ className, ...props }: ComponentProps<"table">) {
  return <table data-slot="table" className={cn("w-full caption-bottom border-collapse text-sm", className)} {...props} />;
}

export function TableHeader({ className, ...props }: ComponentProps<"thead">) {
  return <thead data-slot="table-header" className={cn("bg-surface-2/95 backdrop-blur-sm", className)} {...props} />;
}

export function TableBody({ className, ...props }: ComponentProps<"tbody">) {
  return <tbody data-slot="table-body" className={cn("[&_tr:last-child]:border-0", className)} {...props} />;
}

export function TableRow({ className, ...props }: ComponentProps<"tr">) {
  return <tr data-slot="table-row" className={cn("border-b border-line/70 transition-colors", className)} {...props} />;
}

export function TableHead({ className, ...props }: ComponentProps<"th">) {
  return (
    <th data-slot="table-head"
        className={cn("whitespace-nowrap border-b border-line px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-muted", className)}
        {...props} />
  );
}

export function TableCell({ className, ...props }: ComponentProps<"td">) {
  return <td data-slot="table-cell" className={cn("whitespace-nowrap px-3 py-2.5 text-ink-2", className)} {...props} />;
}

export function TableCaption({ className, ...props }: ComponentProps<"caption">) {
  return <caption data-slot="table-caption" className={cn("sr-only", className)} {...props} />;
}
