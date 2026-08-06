"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Agenda, Facet, FacetStatus, SpendSummary } from "@/lib/types";
import FacetCard from "@/components/FacetCard";
import { Button, Card, EmptyState, PageHeader, Skeleton, StatGrid, StatTile } from "@/components/ui";
import { formatMoney } from "@/lib/format";

const WINDOWS = [7, 30, 90, 365];

function windowLabel(days: number): string {
  return days === 365 ? "1 year" : `${days} days`;
}

function Group({
  title,
  facets,
  overdue,
  onStatusChange,
}: {
  title: string;
  facets: Facet[];
  overdue?: boolean;
  onStatusChange: (id: number, status: FacetStatus) => void;
}) {
  if (!facets.length) return null;
  return (
    <section className="mb-7">
      <h2
        className={`mb-3 text-sm font-semibold tracking-wide uppercase ${
          overdue ? "text-danger" : "text-muted"
        }`}
      >
        {title} ({facets.length})
      </h2>
      <div className="flex flex-col gap-2.5">
        {facets.map((facet) => (
          <FacetCard key={facet.id} facet={facet} overdue={overdue} onStatusChange={onStatusChange} />
        ))}
      </div>
    </section>
  );
}

export default function AgendaPage() {
  const [agenda, setAgenda] = useState<Agenda | null>(null);
  const [spend, setSpend] = useState<SpendSummary | null>(null);
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      const [agendaRes, subs] = await Promise.all([
        api.agenda(days),
        api.listFacets({ kind: "subscription", status: "open" }),
      ]);
      if (cancelled) return;
      setAgenda(agendaRes);
      setSpend(subs.spend);
      setLoading(false);
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [days]);

  // Acting on an item removes it locally rather than refetching — the server
  // is already updated, and the list shouldn't jump around underneath a click.
  const handleStatusChange = useCallback((id: number) => {
    setAgenda((prev) =>
      prev
        ? {
            ...prev,
            overdue: prev.overdue.filter((f) => f.id !== id),
            due_today: prev.due_today.filter((f) => f.id !== id),
            upcoming: prev.upcoming.filter((f) => f.id !== id),
          }
        : prev,
    );
  }, []);

  const total = agenda ? agenda.overdue.length + agenda.due_today.length + agenda.upcoming.length : 0;
  const monthlySpend = spend ? Object.entries(spend.monthly_by_currency) : [];

  return (
    <>
      <PageHeader
        title="Today"
        description="What's due, what's overdue, and what's coming up."
        actions={
          <div className="inline-flex rounded-lg border border-border bg-surface-sunken p-1">
            {WINDOWS.map((option) => (
              <button
                key={option}
                onClick={() => setDays(option)}
                className={`cursor-pointer rounded-md px-3 py-1.5 text-sm font-medium transition ${
                  days === option
                    ? "bg-surface text-foreground shadow-soft"
                    : "text-muted hover:text-foreground"
                }`}
              >
                {option === 365 ? "1y" : `${option}d`}
              </button>
            ))}
          </div>
        }
      />

      {/* The numbers worth knowing before reading a single card. */}
      {agenda && (
        <div className="mb-7">
          <StatGrid>
            <StatTile
              label="Overdue"
              value={agenda.overdue.length}
              hint={agenda.overdue.length ? "Needs attention" : "All clear"}
              tone={agenda.overdue.length ? "danger" : "success"}
            />
            <StatTile label="Due today" value={agenda.due_today.length} />
            <StatTile label={`Next ${windowLabel(days)}`} value={agenda.upcoming.length} />
            <StatTile
              label="Recurring / mo"
              value={
                monthlySpend.length
                  ? monthlySpend.map(([code, amount]) => formatMoney(amount, code)).join(" · ")
                  : "—"
              }
              hint={
                spend && spend.counted
                  ? `${spend.counted} subscription${spend.counted === 1 ? "" : "s"}${
                      spend.unpriced ? ` · ${spend.unpriced} unpriced` : ""
                    }`
                  : "No subscriptions tracked"
              }
            />
          </StatGrid>
        </div>
      )}

      {loading && !agenda && (
        <div className="space-y-2.5">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
      )}

      {agenda && total === 0 && (
        <EmptyState
          icon="🗓️"
          title={`Nothing due in the next ${windowLabel(days)}`}
          description="Anything you save with a date — a renewal, a deadline, a reminder, an expiring document — comes back to you here."
          action={
            <Link href="/add">
              <Button>Capture something</Button>
            </Link>
          }
        />
      )}

      {agenda && total > 0 && (
        <>
          <Group title="Overdue" facets={agenda.overdue} overdue onStatusChange={handleStatusChange} />
          <Group title="Today" facets={agenda.due_today} onStatusChange={handleStatusChange} />
          <Group title="Upcoming" facets={agenda.upcoming} onStatusChange={handleStatusChange} />
        </>
      )}

      {agenda && total > 0 && (
        <Card className="mt-2 flex flex-wrap items-center justify-between gap-3 bg-surface-raised">
          <p className="text-sm text-muted">Looking for something that isn&apos;t dated?</p>
          <div className="flex gap-2">
            <Link href="/library">
              <Button variant="secondary" size="sm">
                Browse library
              </Button>
            </Link>
            <Link href="/ask">
              <Button variant="secondary" size="sm">
                Ask a question
              </Button>
            </Link>
          </div>
        </Card>
      )}
    </>
  );
}
