import Link from "next/link";
import { notFound } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import EntryDetail from "@/components/EntryDetail";

export default async function EntryPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  const entry = await api.getEntry(id).catch((err) => {
    if (err instanceof ApiError) return null;
    throw err;
  });

  if (!entry) notFound();

  return (
    <div>
      <Link href="/library" className="text-sm text-muted hover:text-accent">
        &larr; Back to library
      </Link>
      <div className="mt-4 rounded-[10px] border border-border bg-surface p-6 shadow-sm">
        <EntryDetail entry={entry} mode="page" />
      </div>
    </div>
  );
}
