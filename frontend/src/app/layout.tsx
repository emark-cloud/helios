import type { Metadata } from "next";
import type { ReactNode } from "react";

import "@/styles/globals.css";

import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "Helios",
  description:
    "A programmatic capital market for AI trading agents on Kite.",
  other: {
    // Per DESIGN.md §14.4 — dark mode only.
    "color-scheme": "dark",
  },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
