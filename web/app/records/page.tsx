"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { Facet, FacetKind, Skill, SpendSummary } from "@/lib/types";
import { formatDue, formatMoney, relativeDue, titleCase } from "@/lib/format";
import { secondaryBtn } from "@/lib/ui";

/** Render one cell. Arrays are common (technologies, ingredients, attendees). */
function Cell({ value }: { value: unknown }) {
  if (value === null || value === undefined || value === "") return <span className="text-muted">—</span>;
  if (Array.isArray(value)) {
    if (!value.length) return <span className="text-muted">—</span>;
    return (
      <div className="flex flex-wrap gap-1">
        {value.map((v, i) => (
          <span key={i} className="rounded-full border border-border px-1.5 py-0.5 text-xs">
            {String(v)}
          </span>
        ))}
      </div>
    );
  }
  if (typeof value === "object") return <span>{JSON.stringify(value)}</span>;
  return <span>{String(value)}</span>;
}

export default function RecordsPage() {
  const [kinds, setKinds] = useState<FacetKind[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [active, setActive] = useState<string>("");
  const [facets, setFacets] = useState<Facet[]>([]);
  const [spend, setSpend] = useState<SpendSummary | null>(null);
  const [showDone, setShowDone] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      const [kindsRes, skillsRes] = await Promise.all([api.listFacetKinds(), api.listSkills()]);
      if (cancelled) return;
      setKinds(kindsRes.kinds);
      setSkills(skillsRes.skills);
      setActive((prev) => prev || kindsRes.kinds[0]?.kind || "");
      if (!kindsRes.kinds.length) setLoading(false);
    }

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const loadFacets = useCallback(async (kind: string, includeDone: boolean) => {
    if (!kind) return;
    setLoading(true);
    const res = await api.listFacets({ kind, status: includeDone ? undefined : "open" });
    setFacets(res.facets);
    setSpend(res.spend);
    setLoading(false);
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      if (cancelled) return;
      await loadFacets(active, showDone);
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [active, showDone, loadFacets]);

  const skill = skills.find((s) => s.id === active);

  // Columns come from the skill's own field list, narrowed to those that
  // actually hold a value in this set -- a skill with eight fields where six
  // are always empty shouldn't render six empty columns.
  const columns = useMemo(() => {
    const declared = skill?.fields ?? [];
    const populated = declared.filter((field) =>
      facets.some((f) => {
        const v = (f.data as Record<string, unknown>)[field];
        return v !== null && v !== undefined && v !== "" && !(Array.isArray(v) && !v.length);
      })
    );
    return populated.length ? populated : declared;
  }, [skill, facets]);

  const dueColumn = skill?.promotes?.due_at;

  async function setStatus(facet: Facet, status: "done" | "open") {
    await api.setFacetStatus(facet.id, status);
    loadFacets(active, showDone);
  }

  if (!kinds.length) {
    return (
      <p className="text-sm text-muted">
        No records yet. Save something and any structured records it produces — subscriptions,
        accounts, projects — show up here, grouped by kind.
      </p>
    );
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap gap-1.5">
        {kinds.map((k) => (
          <button
            key={k.kind}
            onClick={() => setActive(k.kind)}
            className={`rounded-full border px-3.5 py-1.5 text-sm cursor-pointer ${
              active === k.kind ? "border-accent font-semibold text-accent" : "border-border text-muted"
            }`}
          >
            {k.kind} <span className="opacity-60">{k.count}</span>
          </button>
        ))}
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-3">
        {skill && <p className="flex-1 text-xs text-muted">{skill.description}</p>}
        <label className="flex shrink-0 items-center gap-1.5 text-xs text-muted">
          <input
            type="checkbox"
            checked={showDone}
            onChange={(e) => setShowDone(e.target.checked)}
            className="size-4 accent-accent cursor-pointer"
          />
          Include done
        </label>
      </div>

      {spend && Object.keys(spend.monthly_by_currency).length > 0 && (
        <div className="mb-4 rounded-[10px] border border-border bg-surface p-3.5 shadow-sm">
          <span className="text-xs font-semibold uppercase tracking-wide text-muted">Per month</span>
          <div className="mt-1 flex flex-wrap gap-4">
            {Object.entries(spend.monthly_by_currency).map(([currency, total]) => (
              <span key={currency} className="text-lg font-bold">
                {formatMoney(total, currency)}
              </span>
            ))}
          </div>
        </div>
      )}

      {loading ? (
        <p className="text-sm text-muted">Loading...</p>
      ) : !facets.length ? (
        <p className="text-sm text-muted">Nothing here{showDone ? "" : " that's still open"}.</p>
      ) : (
        <div className="overflow-x-auto rounded-[10px] border border-border bg-surface shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left">
                <th className="whitespace-nowrap px-3 py-2 text-xs font-semibold uppercase tracking-wide text-muted">
                  Record
                </th>
                {columns.map((field) => (
                  <th
                    key={field}
                    className="whitespace-nowrap px-3 py-2 text-xs font-semibold uppercase tracking-wide text-muted"
                  >
                    {titleCase(field)}
                    {field === dueColumn && <span className="ml-1 text-accent" title="Shows on the agenda">•</span>}
                  </th>
                ))}
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {facets.map((facet) => (
                <tr key={facet.id} className="border-b border-border last:border-b-0 align-top">
                  <td className="px-3 py-2">
                    <Link href={`/library/${facet.entry_id}`} className="font-medium text-accent">
                      {facet.label || facet.entry_title || `#${facet.id}`}
                    </Link>
                    {facet.due_at && (
                      <div className="text-xs text-muted">
                        {formatDue(facet.due_at)} · {relativeDue(facet.due_at)}
                      </div>
                    )}
                    {facet.status !== "open" && (
                      <div className="text-xs text-muted">{facet.status}</div>
                    )}
                  </td>
                  {columns.map((field) => (
                    <td key={field} className="px-3 py-2">
                      <Cell value={(facet.data as Record<string, unknown>)[field]} />
                    </td>
                  ))}
                  <td className="px-3 py-2 text-right">
                    <button
                      onClick={() => setStatus(facet, facet.status === "open" ? "done" : "open")}
                      className={`${secondaryBtn} whitespace-nowrap px-2.5 py-1 text-xs`}
                    >
                      {facet.status === "open" ? "Done" : "Reopen"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
