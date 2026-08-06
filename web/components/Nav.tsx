"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { MANAGE_TABS } from "@/lib/nav";

/**
 * Navigation is split by how often you reach for something.
 *
 * The old bar listed all eight pages flat, which put "System" -- opened maybe
 * twice a month -- at the same weight as "Ask". These four are the daily loop
 * (see what's due, browse, query, explore); capture is the one thing you do
 * most, so it's a button rather than a tab it would have to win against; and
 * the three configuration pages live behind the gear, where they share a
 * sub-nav instead of each claiming a top-level slot.
 */

type NavItem = {
  href: string;
  label: string;
  /** Extra path prefixes that should still light this item up. */
  also?: string[];
  icon: React.ReactNode;
};

const stroke = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.6,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

function Icon({ children }: { children: React.ReactNode }) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" {...stroke}>
      {children}
    </svg>
  );
}

const PRIMARY: NavItem[] = [
  {
    href: "/agenda",
    label: "Today",
    icon: (
      <Icon>
        <rect x="3" y="5" width="18" height="16" rx="2" />
        <path d="M3 10h18M8 3v4M16 3v4" />
      </Icon>
    ),
  },
  {
    href: "/library",
    label: "Library",
    also: ["/records"],
    icon: (
      <Icon>
        <path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H9v16H5.5A1.5 1.5 0 0 1 4 18.5z" />
        <path d="M9 4h5.5A1.5 1.5 0 0 1 16 5.5v13a1.5 1.5 0 0 1-1.5 1.5H9" />
        <path d="M18 6.5l2 12" />
      </Icon>
    ),
  },
  {
    href: "/ask",
    label: "Ask",
    icon: (
      <Icon>
        <circle cx="11" cy="11" r="7" />
        <path d="M16.5 16.5L21 21" />
      </Icon>
    ),
  },
  {
    href: "/graph",
    label: "Graph",
    icon: (
      <Icon>
        <circle cx="6" cy="7" r="2.5" />
        <circle cx="18" cy="6" r="2.5" />
        <circle cx="12" cy="18" r="2.5" />
        <path d="M8 8.5l3 7M16.5 8l-3.5 8M8.4 6.6l7.2-.3" />
      </Icon>
    ),
  },
];

const CaptureIcon = (
  <Icon>
    <path d="M12 5v14M5 12h14" />
  </Icon>
);

const GearIcon = (
  <Icon>
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-2.9 1.2v.2a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0-1.2-2.9H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.2-2.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3 1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 2.9 1.2l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" />
  </Icon>
);

export function isActive(pathname: string, item: { href: string; also?: string[] }): boolean {
  return [item.href, ...(item.also ?? [])].some(
    (path) => pathname === path || pathname.startsWith(`${path}/`),
  );
}

export default function Nav() {
  const pathname = usePathname();
  const manageActive = MANAGE_TABS.some((tab) => isActive(pathname, tab));

  return (
    <>
      <header className="sticky top-0 z-20 border-b border-border bg-surface/85 backdrop-blur">
        <div className="mx-auto flex max-w-4xl items-center gap-3 px-5 py-3">
          <Link href="/agenda" className="flex items-center gap-2 text-[1.05rem] font-bold tracking-tight">
            <span className="grid h-7 w-7 place-items-center rounded-md bg-accent text-white">
              <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true" {...stroke} strokeWidth={2.2}>
                <path d="M5 12.5l4.5 4.5L19 7" />
              </svg>
            </span>
            Lifelog
          </Link>

          {/* Desktop primary nav. On mobile this lives in the bottom bar. */}
          <nav className="ml-4 hidden flex-1 items-center gap-1 sm:flex">
            {PRIMARY.map((item) => {
              const active = isActive(pathname, item);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={`flex items-center gap-2 rounded-full px-3.5 py-2 text-sm transition ${
                    active
                      ? "bg-accent-soft font-semibold text-accent"
                      : "text-muted hover:bg-surface-raised hover:text-foreground"
                  }`}
                >
                  {item.icon}
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <div className="ml-auto flex items-center gap-2 sm:ml-0">
            <Link
              href="/add"
              className="inline-flex items-center gap-1.5 rounded-full bg-accent px-4 py-2 text-sm font-semibold text-white shadow-soft transition hover:bg-accent-hover"
            >
              {CaptureIcon}
              <span className="hidden sm:inline">Capture</span>
              <span className="sm:hidden">Add</span>
            </Link>
            <Link
              href="/system"
              aria-label="Settings"
              aria-current={manageActive ? "page" : undefined}
              className={`rounded-full p-2.5 transition ${
                manageActive
                  ? "bg-accent-soft text-accent"
                  : "text-muted hover:bg-surface-raised hover:text-foreground"
              }`}
            >
              {GearIcon}
            </Link>
          </div>
        </div>
      </header>

      {/* Mobile: thumb-reachable tab bar. The header keeps capture and settings. */}
      <nav className="fixed inset-x-0 bottom-0 z-20 border-t border-border bg-surface/95 backdrop-blur sm:hidden">
        <div className="mx-auto flex max-w-md">
          {PRIMARY.map((item) => {
            const active = isActive(pathname, item);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`flex flex-1 flex-col items-center gap-1 py-2.5 text-[0.6875rem] font-medium transition ${
                  active ? "text-accent" : "text-muted"
                }`}
              >
                {item.icon}
                {item.label}
              </Link>
            );
          })}
        </div>
      </nav>
    </>
  );
}
