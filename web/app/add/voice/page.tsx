"use client";

import dynamic from "next/dynamic";

// MediaRecorder needs the browser -- never render this on the server, and
// only pull its JS into the bundle when the user actually opens this tab.
const VoiceRecorder = dynamic(() => import("@/components/VoiceRecorder"), {
  ssr: false,
  loading: () => <p className="text-sm text-muted">Loading recorder...</p>,
});

export default function AddVoicePage() {
  return <VoiceRecorder />;
}
