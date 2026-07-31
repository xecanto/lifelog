import { titleCase } from "@/lib/format";

function FieldValue({ value }: { value: unknown }) {
  if (Array.isArray(value)) {
    if (!value.length) return <span className="text-muted">—</span>;
    return (
      <ul className="list-disc space-y-0.5 pl-5">
        {value.map((v, i) => (
          <li key={i}>{String(v)}</li>
        ))}
      </ul>
    );
  }
  if (value === null || value === undefined || value === "") return <span className="text-muted">—</span>;
  if (typeof value === "object") return <span>{JSON.stringify(value)}</span>;
  return <span>{String(value)}</span>;
}

/** Key/value rendering for a bag of extracted fields (entry metadata, facet data). */
export default function FieldList({
  fields,
  hide,
}: {
  fields: Record<string, unknown>;
  hide?: Set<string>;
}) {
  const entries = Object.entries(fields).filter(([key, value]) => {
    if (hide?.has(key)) return false;
    // An empty field is noise here — the point of this list is what's known.
    return !(value === null || value === undefined || value === "" || (Array.isArray(value) && !value.length));
  });

  if (!entries.length) return null;

  return (
    <dl className="space-y-2 text-sm">
      {entries.map(([key, value]) => (
        <div key={key}>
          <dt className="text-xs font-semibold uppercase tracking-wide text-muted">{titleCase(key)}</dt>
          <dd className="mt-0.5">
            <FieldValue value={value} />
          </dd>
        </div>
      ))}
    </dl>
  );
}
