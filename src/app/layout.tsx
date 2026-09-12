import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Ledger-X | Financial System of Record",
  description: "Modern, secure, scalable and auditable digital ledger and financial management platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-ledger-bg text-slate-100 antialiased selection:bg-brand-500 selection:text-white">
        {children}
      </body>
    </html>
  );
}
