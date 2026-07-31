"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/add", label: "Add" },
  { href: "/agenda", label: "Agenda" },
  { href: "/library", label: "Library" },
  { href: "/ask", label: "Ask" },
  { href: "/graph", label: "Graph" },
  { href: "/skills", label: "Skills" },
  { href: "/system", label: "System" },
];

export default function Nav() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-10 border-b border-border bg-surface">
      <div className="mx-auto flex max-w-3xl items-center justify-between px-5 py-4">
        <Link href="/add" className="text-[1.1rem] font-bold tracking-tight">
          Lifelog
        </Link>
        <nav className="flex gap-1">
          {LINKS.map((link) => {
            const active = pathname === link.href || pathname.startsWith(`${link.href}/`);
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`rounded-full px-4 py-2 text-sm ${
                  active ? "bg-accent-soft font-semibold text-accent" : "text-muted hover:text-foreground"
                }`}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
