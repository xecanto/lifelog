"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import type { Entry } from "@/lib/types";
import StatusMessage from "@/components/StatusMessage";
import ClarifyPanel from "@/components/ClarifyPanel";
import { Badge, Card, PageHeader } from "@/components/ui";
import { titleCase } from "@/lib/format";
import { primaryBtn, secondaryBtn } from "@/lib/ui";

const URL_RE = /^(https?:\/\/\S+|(?:www\.)?[a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)*\.[a-z]{2,}(?:\/\S*)?)$/i;

function describeFile(file: File): string {
  const type = file.type || "";
  if (type.startsWith("image/")) return "image";
  if (type.startsWith("audio/") || type === "video/mp4") return "audio";
  return "document";
}

/** Mirrors app/ingest/capture.py so the UI can say what it's about to do. */
function describeInput(text: string, files: File[]): string {
  if (files.length === 1) {
    const kind = describeFile(files[0]);
    if (kind === "image") return "Image — described so you can search it";
    if (kind === "audio") return "Audio — transcribed on your machine";
    return "Document — text will be extracted";
  }
  if (files.length > 1) {
    // Several files become ONE entry, which is the surprising part worth
    // saying out loud before the user hits save.
    const kinds = [...new Set(files.map(describeFile))];
    return `${files.length} ${kinds.join(" + ")} files → one entry`;
  }
  const trimmed = text.trim();
  if (!trimmed) return "";
  if (URL_RE.test(trimmed)) return "Link — the article will be fetched";
  return "Note";
}

export default function AddPage() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<{ text: string; kind?: "error" | "success" }>({ text: "" });
  const [saved, setSaved] = useState<Entry | null>(null);

  function reset() {
    setText("");
    setFiles([]);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  function addFiles(incoming: FileList | File[] | null) {
    const list = Array.from(incoming ?? []);
    if (list.length) setFiles((prev) => [...prev, ...list]);
  }

  async function toggleRecording() {
    if (recording) {
      mediaRecorderRef.current?.stop();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      chunksRef.current = [];
      const recorder = new MediaRecorder(stream);
      recorder.ondataavailable = (e) => chunksRef.current.push(e.data);
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        addFiles([new File([blob], `recording-${Date.now()}.webm`, { type: "audio/webm" })]);
        stream.getTracks().forEach((t) => t.stop());
        setRecording(false);
      };
      recorder.start();
      mediaRecorderRef.current = recorder;
      setRecording(true);
      setStatus({ text: "" });
    } catch {
      setStatus({ text: "Microphone access denied or unavailable.", kind: "error" });
    }
  }

  // A pasted screenshot arrives as a file on the clipboard, not as text.
  function handlePaste(e: React.ClipboardEvent) {
    const pasted = Array.from(e.clipboardData.files);
    if (pasted.length) {
      e.preventDefault();
      addFiles(pasted);
    }
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    addFiles(e.dataTransfer.files);
  }

  async function submit() {
    if (!text.trim() && !files.length) {
      return setStatus({ text: "Type something, or drop in a file.", kind: "error" });
    }
    setBusy(true);
    setStatus({ text: "" });
    setSaved(null);
    try {
      const entry = await api.capture({ text: text.trim() || undefined, files });
      reset();
      setSaved(entry);
    } catch (err) {
      setStatus({ text: err instanceof ApiError ? err.message : "Something went wrong.", kind: "error" });
    } finally {
      setBusy(false);
    }
  }

  const detected = describeInput(text, files);

  return (
    <div>
      <PageHeader
        title="Capture"
        description="One box for everything. Type it, paste it, drop a file, or record a memo — the assistant works out what it is."
      />
      <div
        onDrop={handleDrop}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        className={`rounded-lg border-2 bg-surface p-4 shadow-soft transition ${
          dragging ? "border-dashed border-accent bg-accent-soft/40" : "border-border"
        }`}
      >
        <textarea
          className="w-full resize-y bg-transparent text-sm outline-none placeholder:text-subtle"
          rows={7}
          placeholder="Anything — a thought, a link, what you just signed up for… or drop a file, paste a screenshot, or record a memo."
          value={text}
          onChange={(e) => setText(e.target.value)}
          onPaste={handlePaste}
        />

        {files.length > 0 && (
          <div className="mt-2 flex flex-col gap-1.5">
            {files.map((f, i) => (
              <div
                key={`${f.name}-${i}`}
                className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm"
              >
                <span className="min-w-0 flex-1 truncate">{f.name}</span>
                <span className="shrink-0 text-xs text-muted">{Math.round(f.size / 1024)} KB</span>
                <button
                  onClick={() => setFiles((prev) => prev.filter((_, index) => index !== i))}
                  className="shrink-0 text-xs text-muted cursor-pointer hover:text-accent"
                >
                  remove
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button className={secondaryBtn} onClick={() => fileInputRef.current?.click()} type="button">
            Attach
          </button>
          <button className={secondaryBtn} onClick={toggleRecording} type="button">
            {recording ? "■ Stop" : "● Record"}
          </button>
          {recording && <span className="text-sm text-muted">Recording...</span>}
          <span className="ml-auto text-xs text-muted">{detected}</span>
        </div>

        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          onChange={(e) => {
            addFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      <button className={primaryBtn} onClick={submit} disabled={busy}>
        {busy ? "Organizing..." : "Save"}
      </button>
      <StatusMessage text={status.text} kind={status.kind} />

      {saved && (
        <Card className="mt-4">
          <p className="text-xs font-semibold tracking-wide text-muted uppercase">Saved</p>
          <Link href={`/library/${saved.id}`} className="mt-1 block font-semibold text-accent">
            {saved.title}
          </Link>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <Badge tone="accent">{saved.category}</Badge>
            {saved.facets.map((f) => (
              <Badge key={f.id}>
                {f.kind}
                {f.due_at ? ` · ${f.due_at.slice(0, 10)}` : ""}
              </Badge>
            ))}
          </div>
          {saved.summary && <p className="mt-2 text-sm text-muted">{saved.summary}</p>}

          {(saved.updated_records ?? []).length > 0 && (
            <div className="mt-3 border-t border-border pt-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted">
                Updated, not duplicated
              </p>
              {saved.updated_records!.map((record) => (
                <p key={record.facet_id} className="mt-1 text-sm">
                  <Link href={`/records`} className="font-medium text-accent">
                    {record.label || record.kind}
                  </Link>{" "}
                  <span className="text-muted">
                    {record.changed_fields.length
                      ? `— changed ${record.changed_fields.map(titleCase).join(", ").toLowerCase()}`
                      : "— nothing new to record"}
                  </span>
                </p>
              ))}
            </div>
          )}
        </Card>
      )}

      {saved && <ClarifyPanel questions={saved.pending_questions ?? []} onAnswered={setSaved} />}
    </div>
  );
}
