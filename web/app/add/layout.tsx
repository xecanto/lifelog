"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/add/text", label: "Text" },
  { href: "/add/link", label: "Link" },
  { href: "/add/file", label: "File" },
  { href: "/add/image", label: "Image" },
  { href: "/add/voice", label: "Voice" },
];

export default function AddLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div>
      <div className="mb-4 flex flex-wrap gap-1.5">
        {TABS.map((tab) => {
          const active = pathname === tab.href;
          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={`rounded-full border px-3.5 py-1.5 text-sm ${
                active ? "border-accent font-semibold text-accent" : "border-border text-muted"
              }`}
            >
              {tab.label}
            </Link>
          );
        })}
      </div>
      <div className="rounded-[10px] border border-border bg-surface p-5 shadow-sm">{children}</div>
    </div>
  );
}
