import "@fontsource-variable/inter";
import "./globals.css";

import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import { AppShell } from "@/components/AppShell";
import { MetaProvider } from "@/components/MetaProvider";
import { THEME_SCRIPT } from "@/components/ThemeToggle";

export const metadata: Metadata = {
  title: { default: "FairLend Watch", template: "%s · FairLend Watch" },
  description: "Lending conduct monitor. Synthetic data. A flag is a prompt for a human to look, not a verdict.",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [{ media: "(prefers-color-scheme: light)", color: "#ffffff" }],
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="font-sans">
        <MetaProvider>
          <AppShell>{children}</AppShell>
        </MetaProvider>
      </body>
    </html>
  );
}
