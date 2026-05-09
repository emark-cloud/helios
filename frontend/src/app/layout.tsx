import type { Metadata } from "next";
import Script from "next/script";
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
        {/* Particle's pino logger reads process.stdout.isTTY during
         * passkey signing and webpack 5's browser shim only defines
         * process.env. `beforeInteractive` runs the polyfill before
         * any client chunk hydrates — including Particle's lazy
         * import — so the global exists when its logger initializes.
         * An in-bundle polyfill races the dynamic import on some
         * builds and surfaces "Cannot read properties of undefined
         * (reading 'isTTY')" mid-userOp. */}
        <Script src="/process-tty-polyfill.js" strategy="beforeInteractive" />
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
