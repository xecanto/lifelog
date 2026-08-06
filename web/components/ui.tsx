/**
 * The shared visual vocabulary.
 *
 * Pages compose these rather than repeating utility strings, so a change to
 * what a card or a button looks like happens once. Everything here is a server
 * component -- none of it holds state -- so it can be used from any page
 * without dragging it across the client boundary.
 */

import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";

function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

/* -------------------------------------------------------------------------
   Page scaffolding
------------------------------------------------------------------------- */

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1.5 text-sm text-muted">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </header>
  );
}

export function Section({
  title,
  description,
  actions,
  children,
}: {
  title?: string;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="mb-8">
      {(title || actions) && (
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <div>
            {title && <h2 className="text-sm font-semibold tracking-wide text-muted uppercase">{title}</h2>}
            {description && <p className="mt-1 text-sm text-muted">{description}</p>}
          </div>
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

/* -------------------------------------------------------------------------
   Containers
------------------------------------------------------------------------- */

export function Card({
  children,
  className,
  padded = true,
  ...rest
}: { children: ReactNode; padded?: boolean } & ComponentProps<"div">) {
  return (
    <div
      {...rest}
      className={cx(
        "rounded-lg border border-border bg-surface shadow-soft",
        padded && "p-5",
        className,
      )}
    >
      {children}
    </div>
  );
}

/** A card that is also a link. Hover lifts it slightly so it reads as clickable. */
export function CardLink({
  href,
  children,
  className,
}: {
  href: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <Link
      href={href}
      className={cx(
        "block rounded-lg border border-border bg-surface p-5 shadow-soft transition",
        "hover:border-border-strong hover:shadow-card",
        className,
      )}
    >
      {children}
    </Link>
  );
}

/* -------------------------------------------------------------------------
   Controls
------------------------------------------------------------------------- */

const BUTTON_BASE =
  "inline-flex items-center justify-center gap-2 rounded-md text-sm font-medium transition " +
  "disabled:opacity-50 disabled:cursor-default cursor-pointer whitespace-nowrap";

const BUTTON_VARIANTS = {
  primary: "bg-accent text-white hover:bg-accent-hover shadow-soft",
  secondary: "border border-border-strong bg-surface text-foreground hover:bg-surface-raised",
  ghost: "text-muted hover:bg-surface-raised hover:text-foreground",
  danger: "border border-border-strong bg-surface text-danger hover:bg-danger-soft",
} as const;

const BUTTON_SIZES = {
  sm: "px-3 py-1.5 text-[0.8125rem]",
  md: "px-4 py-2.5",
} as const;

export type ButtonVariant = keyof typeof BUTTON_VARIANTS;

export function buttonClass(
  variant: ButtonVariant = "primary",
  size: keyof typeof BUTTON_SIZES = "md",
): string {
  return cx(BUTTON_BASE, BUTTON_VARIANTS[variant], BUTTON_SIZES[size]);
}

export function Button({
  variant = "primary",
  size = "md",
  className,
  ...rest
}: {
  variant?: ButtonVariant;
  size?: keyof typeof BUTTON_SIZES;
} & ComponentProps<"button">) {
  return <button {...rest} className={cx(buttonClass(variant, size), className)} />;
}

export const inputClass =
  "w-full rounded-md border border-border bg-surface px-3.5 py-2.5 text-sm text-foreground " +
  "placeholder:text-subtle outline-none transition focus:border-accent";

/* -------------------------------------------------------------------------
   Status and labels
------------------------------------------------------------------------- */

const BADGE_TONES = {
  neutral: "bg-surface-sunken text-muted",
  accent: "bg-accent-soft text-accent",
  success: "bg-success-soft text-success",
  warning: "bg-warning-soft text-warning",
  danger: "bg-danger-soft text-danger",
} as const;

export type BadgeTone = keyof typeof BADGE_TONES;

export function Badge({
  tone = "neutral",
  children,
  className,
}: {
  tone?: BadgeTone;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium",
        BADGE_TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

/* -------------------------------------------------------------------------
   Numbers
------------------------------------------------------------------------- */

/**
 * One headline number with its label. `hint` is for the secondary reading --
 * the same quantity over a different window, or what it's made of.
 */
export function StatTile({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: BadgeTone;
}) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4 shadow-soft">
      <div className="text-xs font-medium tracking-wide text-muted uppercase">{label}</div>
      <div className="tabular mt-2 text-2xl font-semibold tracking-tight">{value}</div>
      {hint && (
        <div className="mt-1.5 text-xs text-subtle">
          {tone ? <Badge tone={tone}>{hint}</Badge> : hint}
        </div>
      )}
    </div>
  );
}

export function StatGrid({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">{children}</div>;
}

/* -------------------------------------------------------------------------
   Absence
------------------------------------------------------------------------- */

/**
 * What a page shows before it has anything to show. Always says what to do
 * next -- an empty state without an action is a dead end.
 */
export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: ReactNode;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-dashed border-border-strong bg-surface-raised px-6 py-12 text-center">
      {icon && <div className="mb-3 text-3xl opacity-60">{icon}</div>}
      <p className="font-medium">{title}</p>
      {description && <p className="mx-auto mt-1.5 max-w-sm text-sm text-muted">{description}</p>}
      {action && <div className="mt-5 flex justify-center">{action}</div>}
    </div>
  );
}

/** Grey blocks standing in for content that hasn't arrived yet. */
export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("animate-pulse rounded-md bg-surface-sunken", className)} />;
}

export { cx };
