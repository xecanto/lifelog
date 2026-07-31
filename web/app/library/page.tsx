"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { CategoryCount, Entry } from "@/lib/types";
import EntryCard from "@/components/EntryCard";
import { secondaryBtn, textInput } from "@/lib/ui";

const PAGE_SIZE = 30;

export default function LibraryPage() {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [total, setTotal] = useState(0);
  const [categories, setCategories] = useState<CategoryCount[]>([]);
  const [category, setCategory] = useState("");
  const [filterText, setFilterText] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.listCategories().then((res) => setCategories(res.categories));
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      const res = await api.listEntries({ limit: PAGE_SIZE, offset: 0, category: category || undefined });
      if (cancelled) return;
      setEntries(res.entries);
      setTotal(res.total);
      setLoading(false);
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [category]);

  async function loadMore() {
    const res = await api.listEntries({ limit: PAGE_SIZE, offset: entries.length, category: category || undefined });
    setEntries((prev) => [...prev, ...res.entries]);
    setTotal(res.total);
  }

  const filtered = useMemo(() => {
    const q = filterText.trim().toLowerCase();
    if (!q) return entries;
    return entries.filter((e) =>
      [e.title, e.summary, e.category, e.tags.join(" ")].join(" ").toLowerCase().includes(q)
    );
  }, [entries, filterText]);

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2.5">
        <select value={category} onChange={(e) => setCategory(e.target.value)} className="rounded-lg border border-border bg-surface px-3 py-2 text-sm">
          <option value="">All categories</option>
          {categories
            .filter((c) => c.category)
            .map((c) => (
              <option key={c.category} value={c.category}>
                {c.category} ({c.count})
              </option>
            ))}
        </select>
        <input
          type="search"
          placeholder="Filter loaded entries..."
          value={filterText}
          onChange={(e) => setFilterText(e.target.value)}
          className={`${textInput} flex-1 min-w-[160px]`}
        />
        <span className="text-sm text-muted">{total} saved</span>
      </div>

      {loading ? (
        <p className="text-sm text-muted">Loading...</p>
      ) : filtered.length === 0 ? (
        <p className="text-sm text-muted">Nothing here yet.</p>
      ) : (
        <div className="flex flex-col gap-2.5">
          {filtered.map((entry) => (
            <EntryCard key={entry.id} entry={entry} />
          ))}
        </div>
      )}

      {entries.length < total && (
        <button onClick={loadMore} className={`${secondaryBtn} mx-auto mt-4 block`}>
          Load more
        </button>
      )}
    </div>
  );
}
