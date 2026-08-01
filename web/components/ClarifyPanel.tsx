"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Entry, PendingQuestion } from "@/lib/types";
import { secondaryBtn, textInput } from "@/lib/ui";

/** Questions grouped by the record they belong to, preserving order. */
function byFacet(questions: PendingQuestion[]): { facetId: number; kind: string; items: PendingQuestion[] }[] {
  const groups = new Map<number, { facetId: number; kind: string; items: PendingQuestion[] }>();
  for (const question of questions) {
    const existing = groups.get(question.facet_id);
    if (existing) existing.items.push(question);
    else groups.set(question.facet_id, { facetId: question.facet_id, kind: question.kind, items: [question] });
  }
  return [...groups.values()];
}

function FacetQuestions({
  group,
  onAnswered,
}: {
  group: { facetId: number; kind: string; items: PendingQuestion[] };
  onAnswered: (entry: Entry) => void;
}) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const filled = Object.values(answers).some((v) => v.trim());

  async function submit() {
    setBusy(true);
    setError("");
    try {
      // Only send what was actually typed — a blank stays unanswered and
      // will simply be asked again, rather than being recorded as empty.
      const given = Object.fromEntries(Object.entries(answers).filter(([, v]) => v.trim()));
      const { entry, facet } = await api.clarifyFacet(group.facetId, given);
      // A reply like "no idea" is valid but records nothing; without this the
      // question would just silently reappear and look like a failed save.
      if (facet.recorded_fields && facet.recorded_fields.length === 0) {
        setError("Couldn't get a value out of that — try being more specific, or leave it blank.");
        return;
      }
      onAnswered(entry);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save those answers.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-lg border border-border p-3">
      <span className="rounded-full bg-accent-soft px-2 py-0.5 text-xs font-semibold text-accent">
        {group.kind}
      </span>
      <div className="mt-2.5 flex flex-col gap-2.5">
        {group.items.map((question) => (
          <div key={question.field}>
            <label htmlFor={`q-${group.facetId}-${question.field}`} className="text-sm">
              {question.question}
            </label>
            <input
              id={`q-${group.facetId}-${question.field}`}
              className={`${textInput} mt-1`}
              value={answers[question.field] ?? ""}
              placeholder="Skip if you don't know"
              onChange={(e) => setAnswers((prev) => ({ ...prev, [question.field]: e.target.value }))}
              onKeyDown={(e) => {
                if (e.key === "Enter" && filled && !busy) submit();
              }}
            />
          </div>
        ))}
      </div>
      <div className="mt-3 flex items-center gap-2">
        <button onClick={submit} disabled={busy || !filled} className={secondaryBtn}>
          {busy ? "Saving..." : "Save answers"}
        </button>
        {error && <span className="text-xs text-danger">{error}</span>}
      </div>
    </div>
  );
}

export default function ClarifyPanel({
  questions,
  onAnswered,
}: {
  questions: PendingQuestion[];
  onAnswered: (entry: Entry) => void;
}) {
  if (!questions.length) return null;

  return (
    <div className="mt-4 rounded-[10px] border border-border bg-surface p-4 shadow-sm">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">A few things I don&apos;t know</h2>
      <p className="mt-1 text-xs text-muted">
        Answer what you can — anything you skip just stays blank, and you&apos;ll be asked again later.
      </p>
      <div className="mt-3 flex flex-col gap-2.5">
        {byFacet(questions).map((group) => (
          <FacetQuestions key={group.facetId} group={group} onAnswered={onAnswered} />
        ))}
      </div>
    </div>
  );
}
