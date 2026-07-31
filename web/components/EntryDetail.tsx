"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, mediaUrl } from "@/lib/api";
import type { Entry } from "@/lib/types";
import { secondaryBtn } from "@/lib/ui";

const SOURCE_LABEL: Record<string, string> = {
  text: "Note",
  file: "File",
  link: "Link",
  image: "Image",
  voice: "Voice",
};

const HIDDEN_METADATA_KEYS = new Set(["extension", "page_title"]);

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function MetaValue({ value }: { value: unknown }) {
  if (Array.isArray(value)) {
    if (!value.length) return <span className="text-muted">—</span>;
    return (
      <ul className="list-disc space-y-0.5 pl-5">
        {value.map((v, i) => (
          <li key={i}>{String(v)}</li>
        ))}
      </ul>
    );
  }
  if (value === null || value === undefined || value === "") return <span className="text-muted">—</span>;
  return <span>{String(value)}</span>;
}

function titleCase(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function EntryDetail({ entry, mode }: { entry: Entry; mode: "page" | "modal" }) {
  const router = useRouter();
  const [deleting, setDeleting] = useState(false);

  const extraMetadata = Object.entries(entry.metadata || {}).filter(([key]) => !HIDDEN_METADATA_KEYS.has(key));

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
        <span className="rounded-full border border-border px-2 py-0.5 text-xs text-muted">{entry.skill}</span>
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

      {extraMetadata.length > 0 && (
        <dl className="mt-4 space-y-2 rounded-lg border border-border p-3.5 text-sm">
          {extraMetadata.map(([key, value]) => (
            <div key={key}>
              <dt className="text-xs font-semibold uppercase tracking-wide text-muted">{titleCase(key)}</dt>
              <dd className="mt-0.5">
                <MetaValue value={value} />
              </dd>
            </div>
          ))}
        </dl>
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
