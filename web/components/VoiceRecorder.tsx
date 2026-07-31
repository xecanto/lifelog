"use client";

import { useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import StatusMessage from "@/components/StatusMessage";
import { hint, primaryBtn, secondaryBtn } from "@/lib/ui";

export default function VoiceRecorder() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const [recording, setRecording] = useState(false);
  const [recordedUrl, setRecordedUrl] = useState<string | null>(null);
  const [recordedBlob, setRecordedBlob] = useState<Blob | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<{ text: string; kind?: "error" | "success" }>({ text: "" });

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
        setRecordedBlob(blob);
        setRecordedUrl(URL.createObjectURL(blob));
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

  async function submit() {
    const uploaded = fileInputRef.current?.files?.[0];
    const file = uploaded || (recordedBlob ? new File([recordedBlob], "recording.webm", { type: "audio/webm" }) : null);
    if (!file) return setStatus({ text: "Record a memo or choose an audio file first.", kind: "error" });

    setBusy(true);
    setStatus({ text: "" });
    try {
      await api.addVoice(file);
      if (fileInputRef.current) fileInputRef.current.value = "";
      setRecordedBlob(null);
      setRecordedUrl(null);
      setStatus({ text: "Transcribed and saved.", kind: "success" });
    } catch (err) {
      setStatus({ text: err instanceof ApiError ? err.message : "Something went wrong.", kind: "error" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <p className={hint}>Record a memo, or upload an audio file — transcribed locally with Whisper</p>
      <div className="flex items-center gap-3">
        <button className={secondaryBtn} onClick={toggleRecording} type="button">
          {recording ? "■ Stop" : "● Record"}
        </button>
        {recording && <span className="text-sm text-muted">Recording...</span>}
      </div>
      {recordedUrl && <audio src={recordedUrl} controls className="mt-2.5 w-full" />}
      <div className="my-3.5 text-center text-xs text-muted">or</div>
      <input ref={fileInputRef} type="file" accept="audio/*" className="block text-sm text-muted" />
      <button className={primaryBtn} onClick={submit} disabled={busy}>
        {busy ? "Transcribing..." : "Upload & save"}
      </button>
      <StatusMessage text={status.text} kind={status.kind} />
    </div>
  );
}
