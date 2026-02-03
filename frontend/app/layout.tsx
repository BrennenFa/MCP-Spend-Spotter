import type { Metadata } from "next";
import "./globals.css";
import { ThemeProvider } from "@/contexts/ThemeContext";
import Header from "@/components/Header";

export const metadata: Metadata = {
  title: "NC Spend Spotter",
  description: "Explore North Carolina state budget and vendor payment data with AI assistance",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="antialiased">
        <ThemeProvider>
          <div className="flex flex-col h-screen">
            <Header />
            <main className="flex-1 overflow-hidden">
              {children}
            </main>
          </div>
        </ThemeProvider>
      </body>
    </html>
  );
}
