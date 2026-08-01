"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import type { FacetRevision } from "@/lib/types";
import { titleCase } from "@/lib/format";

function show(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) return value.length ? value.join(", ") : "—";
  return String(value);
}

function when(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

/**
 * What a record has been through. Matching can be wrong, so every change
 * keeps the value it replaced — this is what makes that visible.
 */
export default function RecordHistory({ facetId }: { facetId: number }) {
  const [revisions, setRevisions] = useState<FacetRevision[] | null>(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  async function toggle() {
    if (open) return setOpen(false);
    setOpen(true);
    if (revisions) return;
    setLoading(true);
    try {
      const res = await api.facetRevisions(facetId);
      setRevisions(res.revisions);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <button onClick={toggle} className="text-xs text-accent cursor-pointer">
        {open ? "Hide history" : "History"}
      </button>
      {open && (
        <div className="mt-1.5 text-xs">
          {loading ? (
            <span className="text-muted">Loading...</span>
          ) : !revisions?.length ? (
            <span className="text-muted">Never changed since it was first saved.</span>
          ) : (
            <ul className="space-y-1.5">
              {revisions.map((revision) => {
                const fields = Object.entries(revision.changes);
                return (
                  <li key={revision.id}>
                    <span className="text-muted">{when(revision.created_at)}</span>
                    {!fields.length ? (
                      <span className="text-muted"> — mentioned again, nothing changed</span>
                    ) : (
                      <ul className="mt-0.5 space-y-0.5 pl-3">
                        {fields.map(([field, change]) => (
                          <li key={field}>
                            {titleCase(field)}:{" "}
                            <span className="line-through opacity-60">{show(change.from)}</span>{" "}
                            → <span className="font-medium">{show(change.to)}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
