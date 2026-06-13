import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Marketing Strategist",
  description:
    "Evidence-based business profile pipeline. Scrape any business URL and produce a fully-cited structured profile.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      {/* suppressHydrationWarning: browser extensions (Grammarly, etc.) inject
          data-* attributes onto <body> before React hydrates, causing a benign
          server/client mismatch. This silences only that body-level diff. */}
      <body className="min-h-screen font-sans antialiased" suppressHydrationWarning>
        {children}
      </body>
    </html>
  );
}
