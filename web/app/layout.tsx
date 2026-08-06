import type { Metadata } from "next";
import "./globals.css";
import Nav from "@/components/Nav";

export const metadata: Metadata = {
  title: "Lifelog",
  description: "Your personal AI assistant — save anything, ask anything.",
};

export default function RootLayout({
  children,
  modal,
}: Readonly<{
  children: React.ReactNode;
  modal: React.ReactNode;
}>) {
  return (
    // Browser extensions stamp attributes onto <html> and <body> before React
    // hydrates (e.g. data-datablur-ready, style="visibility:visible"), which
    // React reports as a hydration mismatch even though nothing here is wrong.
    // This suppression applies to these two elements only -- real mismatches
    // inside the app still surface.
    <html lang="en" className="h-full antialiased" suppressHydrationWarning>
      <body className="min-h-full flex flex-col" suppressHydrationWarning>
        <Nav />
        {/* pb-24 on small screens clears the fixed mobile tab bar. */}
        <main className="mx-auto w-full max-w-4xl flex-1 px-5 pt-7 pb-24 sm:pb-10">{children}</main>
        {modal}
      </body>
    </html>
  );
}
