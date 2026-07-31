import Link from "next/link";
import type { Entry } from "@/lib/types";

const SOURCE_LABEL: Record<string, string> = {
  text: "Note",
  file: "File",
  link: "Link",
  image: "Image",
  voice: "Voice",
};

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export default function EntryCard({ entry }: { entry: Entry }) {
  return (
    <Link
      href={`/library/${entry.id}`}
      className="block rounded-[10px] border border-border bg-surface p-4 transition-colors hover:border-accent"
    >
      <div className="flex items-baseline justify-between gap-3">
        <div className="font-semibold">{entry.title || "Untitled"}</div>
        <div className="shrink-0 text-xs text-muted">{formatDate(entry.created_at)}</div>
      </div>
      {entry.summary && <p className="mt-1.5 text-sm leading-snug text-muted">{entry.summary}</p>}
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <span className="rounded-full bg-accent-soft px-2.5 py-0.5 text-xs font-semibold text-accent">
          {entry.category || "Other"}
        </span>
        <span className="rounded-full border border-border px-2 py-0.5 text-xs text-muted">
          {SOURCE_LABEL[entry.source_type] || entry.source_type}
        </span>
        {entry.tags.slice(0, 5).map((tag) => (
          <span key={tag} className="rounded-full border border-border px-2 py-0.5 text-xs text-muted">
            {tag}
          </span>
        ))}
      </div>
    </Link>
  );
}
