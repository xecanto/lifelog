"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Entry } from "@/lib/types";
import EntryCard from "@/components/EntryCard";
import { primaryBtn, textInput } from "@/lib/ui";

export default function AskPage() {
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [answer, setAnswer] = useState("");
  const [sources, setSources] = useState<Entry[]>([]);
  const [error, setError] = useState("");

  async function submit() {
    if (!question.trim() || busy) return;
    setBusy(true);
    setAnswer("");
    setSources([]);
    setError("");
    try {
      const res = await api.ask(question);
      setAnswer(res.answer);
      setSources(res.sources);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-[10px] border border-border bg-surface p-5 shadow-sm">
      <div className="flex gap-2.5">
        <input
          type="text"
          className={textInput}
          placeholder="Ask anything about what you've saved..."
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
        />
        <button className={`${primaryBtn} mt-0 shrink-0`} onClick={submit} disabled={busy}>
          {busy ? "Thinking..." : "Ask"}
        </button>
      </div>

      {error && <p className="mt-4 text-sm text-danger">{error}</p>}
      {answer && <p className="mt-5 whitespace-pre-wrap text-[0.98rem] leading-relaxed">{answer}</p>}

      {sources.length > 0 && (
        <div className="mt-5">
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Sources</div>
          <div className="flex flex-col gap-2.5">
            {sources.map((entry) => (
              <EntryCard key={entry.id} entry={entry} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
