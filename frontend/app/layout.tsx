import type { Metadata } from "next";

import { AppHeader } from "../components/AppHeader";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Landing Page Uniqueizer",
  description: "AI-powered landing page uniqueization pipeline.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" data-theme="dark">
      <body className="min-h-screen bg-bg-primary font-sans text-text-primary">
        <div className="min-h-screen bg-bg-primary text-text-primary">
          <AppHeader />

          {children}
        </div>
      </body>
    </html>
  );
}

