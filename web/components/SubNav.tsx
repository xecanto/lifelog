"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/**
 * Tabs between pages that are views of one thing.
 *
 * Entries and Records are the same corpus read two ways, and the three
 * settings pages are one destination; each group used to spend a top-level
 * nav slot saying so. A segmented control says it better and gives the four
 * daily pages room in the main bar.
 */
export default function SubNav({
  tabs,
}: {
  tabs: { href: string; label: string }[];
}) {
  const pathname = usePathname();

  return (
    <div className="mb-6 inline-flex rounded-lg border border-border bg-surface-sunken p-1">
      {tabs.map((tab) => {
        const active = pathname === tab.href || pathname.startsWith(`${tab.href}/`);
        return (
          <Link
            key={tab.href}
            href={tab.href}
            aria-current={active ? "page" : undefined}
            className={`rounded-md px-4 py-1.5 text-sm font-medium transition ${
              active
                ? "bg-surface text-foreground shadow-soft"
                : "text-muted hover:text-foreground"
            }`}
          >
            {tab.label}
          </Link>
        );
      })}
    </div>
  );
}
