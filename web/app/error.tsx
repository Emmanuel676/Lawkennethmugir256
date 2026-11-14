"use client";

import { ErrorState } from "@/components/ui";

export default function PageError({ reset }: { error: Error; reset: () => void }) {
  return (
    <div className="py-8">
      <ErrorState message="Something went wrong while showing this page. No data was changed." onRetry={reset} />
    </div>
  );
}
