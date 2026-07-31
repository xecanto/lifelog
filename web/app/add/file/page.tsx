"use client";

import { useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import StatusMessage from "@/components/StatusMessage";
import { hint, primaryBtn } from "@/lib/ui";

export default function AddFilePage() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<{ text: string; kind?: "error" | "success" }>({ text: "" });

  async function submit() {
    const file = inputRef.current?.files?.[0];
    if (!file) return setStatus({ text: "Choose a file first.", kind: "error" });
    setBusy(true);
    setStatus({ text: "" });
    try {
      await api.addFile(file);
      if (inputRef.current) inputRef.current.value = "";
      setStatus({ text: "File read and saved.", kind: "success" });
    } catch (err) {
      setStatus({ text: err instanceof ApiError ? err.message : "Something went wrong.", kind: "error" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <p className={hint}>PDF, Word (.docx), or plain text (.txt/.md/.csv/.log)</p>
      <input ref={inputRef} type="file" accept=".pdf,.docx,.txt,.md,.markdown,.csv,.log" className="block text-sm text-muted" />
      <button className={primaryBtn} onClick={submit} disabled={busy}>
        {busy ? "Reading..." : "Upload & save"}
      </button>
      <StatusMessage text={status.text} kind={status.kind} />
    </div>
  );
}
