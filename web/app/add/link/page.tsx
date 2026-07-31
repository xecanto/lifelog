"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import StatusMessage from "@/components/StatusMessage";
import { primaryBtn, textInput } from "@/lib/ui";

export default function AddLinkPage() {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<{ text: string; kind?: "error" | "success" }>({ text: "" });

  async function submit() {
    if (!url.trim()) return setStatus({ text: "Paste a URL first.", kind: "error" });
    setBusy(true);
    setStatus({ text: "" });
    try {
      await api.addLink(url);
      setUrl("");
      setStatus({ text: "Fetched, read, and saved.", kind: "success" });
    } catch (err) {
      setStatus({ text: err instanceof ApiError ? err.message : "Something went wrong.", kind: "error" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <input
        type="url"
        className={textInput}
        placeholder="https://example.com/article"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && submit()}
      />
      <button className={primaryBtn} onClick={submit} disabled={busy}>
        {busy ? "Fetching..." : "Fetch & save"}
      </button>
      <StatusMessage text={status.text} kind={status.kind} />
    </div>
  );
}
