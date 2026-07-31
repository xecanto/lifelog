"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Agenda, Facet, FacetStatus, SpendSummary } from "@/lib/types";
import FacetCard from "@/components/FacetCard";
import { formatMoney } from "@/lib/format";

const WINDOWS = [7, 30, 90, 365];

function Section({
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
    <section className="mb-6">
      <h2 className={`mb-2.5 text-sm font-semibold uppercase tracking-wide ${overdue ? "text-danger" : "text-muted"}`}>
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

function SpendCard({ spend }: { spend: SpendSummary }) {
  const currencies = Object.entries(spend.monthly_by_currency);
  if (!currencies.length) return null;
  return (
    <div className="mb-6 rounded-[10px] border border-border bg-surface p-4 shadow-sm">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Recurring, per month</h2>
      <div className="mt-2 flex flex-wrap items-baseline gap-4">
        {currencies.map(([currency, total]) => (
          <span key={currency} className="text-xl font-bold">
            {formatMoney(total, currency)}
          </span>
        ))}
      </div>
      <p className="mt-1.5 text-xs text-muted">
        Across {spend.counted} subscription{spend.counted === 1 ? "" : "s"}
        {spend.unpriced > 0 && ` · ${spend.unpriced} with no price recorded`}
      </p>
    </div>
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
        : prev
    );
  }, []);

  const total = agenda ? agenda.overdue.length + agenda.due_today.length + agenda.upcoming.length : 0;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-1.5">
        {WINDOWS.map((w) => (
          <button
            key={w}
            onClick={() => setDays(w)}
            className={`rounded-full border px-3.5 py-1.5 text-sm cursor-pointer ${
              days === w ? "border-accent font-semibold text-accent" : "border-border text-muted"
            }`}
          >
            {w === 365 ? "1 year" : `${w} days`}
          </button>
        ))}
      </div>

      {spend && <SpendCard spend={spend} />}

      {loading ? (
        <p className="text-sm text-muted">Loading...</p>
      ) : !agenda || total === 0 ? (
        <p className="text-sm text-muted">
          Nothing due in the next {days} days. Anything you save with a date — a renewal, a deadline, a
          reminder, an expiring document — shows up here.
        </p>
      ) : (
        <>
          <Section title="Overdue" facets={agenda.overdue} overdue onStatusChange={handleStatusChange} />
          <Section title="Today" facets={agenda.due_today} onStatusChange={handleStatusChange} />
          <Section title="Upcoming" facets={agenda.upcoming} onStatusChange={handleStatusChange} />
        </>
      )}
    </div>
  );
}
