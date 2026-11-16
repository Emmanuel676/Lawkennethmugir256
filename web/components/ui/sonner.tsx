// shadcn/ui toasts (Sonner), themed with the FairLend brand tokens. Toasts are announced politely to screen readers.
"use client";

import { Toaster as Sonner } from "sonner";

export function Toaster() {
  return (
    <Sonner position="bottom-right" closeButton richColors={false} duration={5000}
      toastOptions={{
        classNames: {
          toast: "!rounded-xl !border !border-line !bg-surface !text-ink !shadow-[0_10px_30px_-10px_rgba(15,23,42,0.35)] !font-sans",
          description: "!text-muted",
          success: "[&_[data-icon]]:!text-[var(--band-low)]",
          error: "[&_[data-icon]]:!text-[var(--band-high)]",
        },
      }} />
  );
}

export { toast } from "sonner";
