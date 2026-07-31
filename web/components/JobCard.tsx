"use client";

import { useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import type { JobStatus, ModificationJob } from "@/lib/types";

const STATUS_STYLE: Record<JobStatus, string> = {
  pending: "border-border text-muted",
  running: "border-accent text-accent",
  succeeded: "border-accent bg-accent-soft text-accent",
  failed: "border-danger text-danger",
  cancelled: "border-border text-muted",
};

export default function JobCard({
  job,
  onChange,
}: {
  job: ModificationJob;
  onChange: (job: ModificationJob) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState(false);

  async function act(action: "run" | "cancel") {
    setBusy(true);
    setError("");
    try {
      const updated =
        action === "run" ? await api.runModification(job.id) : await api.cancelModification(job.id);
      onChange(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  const output = job.error || job.result;

  return (
    <div className="rounded-[10px] border border-border bg-surface p-3.5 shadow-sm">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${STATUS_STYLE[job.status]}`}>
          {job.status}
        </span>
        <span className="rounded-full border border-border px-2 py-0.5 text-xs text-muted">
          {job.kind === "skill" ? "new skill" : "code change"}
        </span>
        {job.origin === "capture" && (
          <span className="rounded-full border border-border px-2 py-0.5 text-xs text-muted">from a note</span>
        )}
        {job.branch && (
          <code className="rounded bg-accent-soft px-1.5 py-0.5 text-xs text-accent">{job.branch}</code>
        )}
      </div>

      <p className="mt-1.5 font-semibold">{job.title || `Job #${job.id}`}</p>
      <p className="mt-1 whitespace-pre-wrap text-sm text-muted">{job.prompt}</p>

      {job.entry_id !== null && (
        <Link href={`/library/${job.entry_id}`} className="mt-1 inline-block text-xs text-accent">
          View the note this came from
        </Link>
      )}

      {output && (
        <div className="mt-2">
          <button onClick={() => setExpanded((v) => !v)} className="text-xs text-accent cursor-pointer">
            {expanded ? "Hide" : job.error ? "Show error" : "Show what changed"}
          </button>
          {expanded && (
            <pre className="mt-1.5 max-h-80 overflow-auto rounded-lg border border-border bg-background p-2.5 text-xs whitespace-pre-wrap">
              {output}
            </pre>
          )}
        </div>
      )}

      {job.status === "pending" && (
        <div className="mt-3 flex items-center gap-2">
          <button
            onClick={() => act("run")}
            disabled={busy}
            className="rounded-lg border border-border px-3 py-1.5 text-xs cursor-pointer hover:border-accent disabled:opacity-50"
          >
            {busy ? "Starting..." : "Run now"}
          </button>
          <button
            onClick={() => act("cancel")}
            disabled={busy}
            className="rounded-lg border border-border px-3 py-1.5 text-xs text-muted cursor-pointer hover:border-accent disabled:opacity-50"
          >
            Cancel
          </button>
          {error && <span className="text-xs text-danger">{error}</span>}
        </div>
      )}
    </div>
  );
}
