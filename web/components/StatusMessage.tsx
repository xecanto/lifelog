export default function StatusMessage({ text, kind }: { text: string; kind?: "error" | "success" }) {
  if (!text) return null;
  return (
    <p className={`mt-3 text-sm ${kind === "error" ? "text-danger" : kind === "success" ? "text-accent" : "text-muted"}`}>
      {text}
    </p>
  );
}
