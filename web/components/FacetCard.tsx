"use client";

import { useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import type { Facet, FacetStatus } from "@/lib/types";
import { formatDue, formatMoney, relativeDue } from "@/lib/format";

/** Extra context worth showing inline, without opening the entry. */
function detailLine(facet: Facet): string {
  const bits: string[] = [];
  if (facet.amount !== null) {
    const money = formatMoney(facet.amount, facet.currency);
    bits.push(facet.cadence && facet.cadence !== "one-time" ? `${money} / ${facet.cadence}` : money);
  }
  if (facet.vendor) bits.push(facet.vendor);
  if (facet.identity) bits.push(facet.identity);
  return bits.join(" · ");
}

export default function FacetCard({
  facet,
  overdue = false,
  onStatusChange,
}: {
  facet: Facet;
  overdue?: boolean;
  onStatusChange?: (id: number, status: FacetStatus) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function update(status: FacetStatus) {
    setBusy(true);
    setError("");
    try {
      await api.setFacetStatus(facet.id, status);
      onStatusChange?.(facet.id, status);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not update.");
      setBusy(false);
    }
  }

  const details = detailLine(facet);

  return (
    <div className="rounded-[10px] border border-border bg-surface p-3.5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="rounded-full bg-accent-soft px-2 py-0.5 text-xs font-semibold text-accent">
              {facet.kind}
            </span>
            {facet.entry_category && (
              <span className="rounded-full border border-border px-2 py-0.5 text-xs text-muted">
                {facet.entry_category}
              </span>
            )}
          </div>
          <p className="mt-1.5 font-semibold">{facet.label || facet.kind}</p>
          {details && <p className="mt-0.5 text-sm text-muted">{details}</p>}
          {facet.entry_title && (
            <Link href={`/library/${facet.entry_id}`} className="mt-1 inline-block text-xs text-accent">
              {facet.entry_title}
            </Link>
          )}
        </div>

        {facet.due_at && (
          <div className="text-right">
            <p className={`text-sm font-semibold ${overdue ? "text-danger" : ""}`}>{relativeDue(facet.due_at)}</p>
            <p className="text-xs text-muted">{formatDue(facet.due_at)}</p>
          </div>
        )}
      </div>

      <div className="mt-3 flex items-center gap-2">
        <button
          onClick={() => update("done")}
          disabled={busy}
          className="rounded-lg border border-border px-3 py-1.5 text-xs cursor-pointer hover:border-accent disabled:opacity-50"
        >
          Done
        </button>
        <button
          onClick={() => update("dismissed")}
          disabled={busy}
          className="rounded-lg border border-border px-3 py-1.5 text-xs text-muted cursor-pointer hover:border-accent disabled:opacity-50"
        >
          Dismiss
        </button>
        {error && <span className="text-xs text-danger">{error}</span>}
      </div>
    </div>
  );
}
