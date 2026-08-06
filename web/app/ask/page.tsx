"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Entry } from "@/lib/types";
import EntryCard from "@/components/EntryCard";
import { Button, Card, EmptyState, inputClass, PageHeader, Skeleton } from "@/components/ui";

/** Shown before the first question, so the page isn't a bare field. */
const EXAMPLES = [
  "What am I paying for every month?",
  "What did I save about that trip?",
  "Which of my accounts need attention?",
];

export default function AskPage() {
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [answer, setAnswer] = useState("");
  const [sources, setSources] = useState<Entry[]>([]);
  const [error, setError] = useState("");
  const [asked, setAsked] = useState(false);

  async function submit(value = question) {
    if (!value.trim() || busy) return;
    setQuestion(value);
    setBusy(true);
    setAnswer("");
    setSources([]);
    setError("");
    setAsked(true);
    try {
      const res = await api.ask(value);
      setAnswer(res.answer);
      setSources(res.sources);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Ask"
        description="Plain-English questions, answered from what you've saved — with the entries it drew on."
      />

      <Card>
        <div className="flex flex-col gap-2.5 sm:flex-row">
          <input
            type="text"
            className={inputClass}
            placeholder="Ask anything about what you've saved..."
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
          />
          <Button onClick={() => submit()} disabled={busy} className="shrink-0">
            {busy ? "Thinking…" : "Ask"}
          </Button>
        </div>

        {error && <p className="mt-4 text-sm text-danger">{error}</p>}

        {busy && (
          <div className="mt-5 space-y-2">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-11/12" />
            <Skeleton className="h-4 w-2/3" />
          </div>
        )}

        {answer && (
          <p className="mt-5 text-[0.98rem] leading-relaxed whitespace-pre-wrap">{answer}</p>
        )}

        {sources.length > 0 && (
          <div className="mt-6 border-t border-border pt-5">
            <div className="mb-3 text-xs font-semibold tracking-wide text-muted uppercase">
              Sources ({sources.length})
            </div>
            <div className="flex flex-col gap-2.5">
              {sources.map((entry) => (
                <EntryCard key={entry.id} entry={entry} />
              ))}
            </div>
          </div>
        )}
      </Card>

      {!asked && (
        <div className="mt-6">
          <EmptyState
            icon="💬"
            title="Try one of these"
            description="Answers come only from your own saved entries — nothing is invented."
            action={
              <div className="flex flex-wrap justify-center gap-2">
                {EXAMPLES.map((example) => (
                  <Button key={example} variant="secondary" size="sm" onClick={() => submit(example)}>
                    {example}
                  </Button>
                ))}
              </div>
            }
          />
        </div>
      )}
    </>
  );
}
