"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import StatusMessage from "@/components/StatusMessage";
import { primaryBtn, textInput } from "@/lib/ui";

export default function AddTextPage() {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<{ text: string; kind?: "error" | "success" }>({ text: "" });

  async function submit() {
    if (!text.trim()) return setStatus({ text: "Write something first.", kind: "error" });
    setBusy(true);
    setStatus({ text: "" });
    try {
      await api.addText(text);
      setText("");
      setStatus({ text: "Saved and organized.", kind: "success" });
    } catch (err) {
      setStatus({ text: err instanceof ApiError ? err.message : "Something went wrong.", kind: "error" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <textarea
        className={textInput}
        rows={8}
        placeholder="Jot down anything — a thought, a fact, a plan..."
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <button className={primaryBtn} onClick={submit} disabled={busy}>
        {busy ? "Organizing..." : "Save note"}
      </button>
      <StatusMessage text={status.text} kind={status.kind} />
    </div>
  );
}
