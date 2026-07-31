"use client";

import { useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import StatusMessage from "@/components/StatusMessage";
import { hint, primaryBtn } from "@/lib/ui";

export default function AddImagePage() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<{ text: string; kind?: "error" | "success" }>({ text: "" });

  function onFileChange() {
    const file = inputRef.current?.files?.[0];
    setPreview(file ? URL.createObjectURL(file) : null);
  }

  async function submit() {
    const file = inputRef.current?.files?.[0];
    if (!file) return setStatus({ text: "Choose an image first.", kind: "error" });
    setBusy(true);
    setStatus({ text: "" });
    try {
      await api.addImage(file);
      if (inputRef.current) inputRef.current.value = "";
      setPreview(null);
      setStatus({ text: "Image described and saved.", kind: "success" });
    } catch (err) {
      setStatus({ text: err instanceof ApiError ? err.message : "Something went wrong.", kind: "error" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <p className={hint}>Claude will describe the image so it becomes searchable text</p>
      <input
        ref={inputRef}
        type="file"
        accept="image/png,image/jpeg,image/gif,image/webp"
        className="block text-sm text-muted"
        onChange={onFileChange}
      />
      {preview && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={preview} alt="Preview" className="mt-2.5 max-h-64 rounded-lg" />
      )}
      <button className={primaryBtn} onClick={submit} disabled={busy}>
        {busy ? "Describing..." : "Upload & save"}
      </button>
      <StatusMessage text={status.text} kind={status.kind} />
    </div>
  );
}
