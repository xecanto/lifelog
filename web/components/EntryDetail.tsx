"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, mediaUrl } from "@/lib/api";
import type { Entry, Facet } from "@/lib/types";
import { secondaryBtn } from "@/lib/ui";
import FieldList from "@/components/FieldList";
import ClarifyPanel from "@/components/ClarifyPanel";
import { formatDue, formatMoney, relativeDue } from "@/lib/format";

const SOURCE_LABEL: Record<string, string> = {
  text: "Note",
  file: "File",
  link: "Link",
  image: "Image",
  voice: "Voice",
};

// `skills` is rendered as badges above; the rest are storage details.
const HIDDEN_METADATA_KEYS = new Set(["extension", "page_title", "skills"]);

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function FacetPanel({ facet }: { facet: Facet }) {
  return (
    <div className="rounded-lg border border-border p-3.5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="rounded-full bg-accent-soft px-2 py-0.5 text-xs font-semibold text-accent">{facet.kind}</span>
        {facet.due_at && (
          <span className="text-xs text-muted">
            {formatDue(facet.due_at)} · {relativeDue(facet.due_at)}
          </span>
        )}
      </div>
      {facet.label && <p className="mt-1.5 text-sm font-semibold">{facet.label}</p>}
      {facet.amount !== null && (
        <p className="mt-0.5 text-sm text-muted">
          {formatMoney(facet.amount, facet.currency)}
          {facet.cadence && facet.cadence !== "one-time" ? ` / ${facet.cadence}` : ""}
        </p>
      )}
      {facet.status !== "open" && <p className="mt-0.5 text-xs text-muted">Marked {facet.status}</p>}
      <div className="mt-2">
        <FieldList fields={facet.data} />
      </div>
    </div>
  );
}

export default function EntryDetail({
  entry: initialEntry,
  mode,
}: {
  entry: Entry;
  mode: "page" | "modal";
}) {
  const router = useRouter();
  const [deleting, setDeleting] = useState(false);
  // Answering a follow-up question rewrites the facets, so this renders from
  // local state rather than the prop.
  const [entry, setEntry] = useState(initialEntry);

  const facets = entry.facets ?? [];
  const skills = Array.isArray(entry.metadata?.skills) ? (entry.metadata.skills as string[]) : [entry.skill];
  const hasVisibleMetadata = Object.entries(entry.metadata || {}).some(
    ([key, value]) => !HIDDEN_METADATA_KEYS.has(key) && value !== null && value !== "" && value !== undefined
  );

  async function handleDelete() {
    if (!confirm("Delete this entry? This can't be undone.")) return;
    setDeleting(true);
    try {
      await api.deleteEntry(entry.id);
      if (mode === "modal") {
        router.back();
        router.refresh();
      } else {
        router.push("/library");
      }
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div>
      <h1 className="pr-8 text-xl font-bold">{entry.title || "Untitled"}</h1>
      <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
        <span className="rounded-full bg-accent-soft px-2.5 py-0.5 text-xs font-semibold text-accent">
          {entry.category || "Other"}
        </span>
        <span className="rounded-full border border-border px-2 py-0.5 text-xs text-muted">
          {SOURCE_LABEL[entry.source_type] || entry.source_type}
        </span>
        {skills.map((skill) => (
          <span key={skill} className="rounded-full border border-border px-2 py-0.5 text-xs text-muted">
            {skill}
          </span>
        ))}
        <span className="rounded-full border border-border px-2 py-0.5 text-xs text-muted">{formatDate(entry.created_at)}</span>
        {entry.tags.map((tag) => (
          <span key={tag} className="rounded-full border border-border px-2 py-0.5 text-xs text-muted">
            {tag}
          </span>
        ))}
      </div>

      {entry.source_type === "image" && entry.file_path && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={mediaUrl(entry.file_path)} alt="" className="mt-4 max-w-full rounded-lg" />
      )}
      {entry.source_type === "voice" && entry.file_path && (
        <audio src={mediaUrl(entry.file_path)} controls className="mt-4 w-full" />
      )}
      {entry.source_url && (
        <p className="mt-3 text-sm">
          <a href={entry.source_url} target="_blank" rel="noopener noreferrer" className="break-all text-accent">
            {entry.source_url}
          </a>
        </p>
      )}

      {entry.summary && <p className="mt-4 text-[0.95rem] italic text-muted">{entry.summary}</p>}

      {facets.length > 0 && (
        <div className="mt-4 flex flex-col gap-2.5">
          {facets.map((facet) => (
            <FacetPanel key={facet.id} facet={facet} />
          ))}
        </div>
      )}

      <ClarifyPanel questions={entry.pending_questions ?? []} onAnswered={setEntry} />

      {hasVisibleMetadata && (
        <div className="mt-4 rounded-lg border border-border p-3.5">
          <FieldList fields={entry.metadata || {}} hide={HIDDEN_METADATA_KEYS} />
        </div>
      )}

      <div className="mt-4 whitespace-pre-wrap text-[0.94rem] leading-relaxed">{entry.raw_text}</div>

      <div className="mt-6">
        <button onClick={handleDelete} disabled={deleting} className={secondaryBtn}>
          {deleting ? "Deleting..." : "Delete entry"}
        </button>
      </div>
    </div>
  );
}
