"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { JobKind, ModificationJob, Provider, Setting, SystemStatus } from "@/lib/types";
import JobCard from "@/components/JobCard";
import StatusMessage from "@/components/StatusMessage";
import { primaryBtn, textInput } from "@/lib/ui";

function SettingRow({
  setting,
  onChange,
  disabled,
}: {
  setting: Setting;
  onChange: (key: string, value: boolean | number | string) => void;
  disabled?: boolean;
}) {
  return (
    <div className={`border-t border-border py-3 first:border-t-0 ${disabled ? "opacity-50" : ""}`}>
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <label htmlFor={setting.key} className="text-sm font-semibold">
            {setting.label}
          </label>
          <p className="mt-0.5 text-xs text-muted">{setting.description}</p>
        </div>
        {setting.type === "bool" ? (
          <input
            id={setting.key}
            type="checkbox"
            checked={Boolean(setting.value)}
            disabled={disabled}
            onChange={(e) => onChange(setting.key, e.target.checked)}
            className="mt-0.5 size-5 shrink-0 accent-accent cursor-pointer disabled:cursor-default"
          />
        ) : setting.choices ? (
          <select
            id={setting.key}
            value={String(setting.value)}
            disabled={disabled}
            onChange={(e) => onChange(setting.key, e.target.value)}
            className="w-52 shrink-0 rounded-lg border border-border bg-background px-3 py-2 text-sm"
          >
            {setting.choices.map((choice) => (
              <option key={choice} value={choice}>
                {choice}
              </option>
            ))}
          </select>
        ) : (
          <input
            id={setting.key}
            type={setting.type === "int" ? "number" : "text"}
            value={String(setting.value)}
            disabled={disabled}
            onChange={(e) =>
              onChange(setting.key, setting.type === "int" ? Number(e.target.value) : e.target.value)
            }
            className={`${textInput} w-52 shrink-0`}
          />
        )}
      </div>
    </div>
  );
}

function ProviderGrid({ providers }: { providers: Provider[] }) {
  return (
    <div className="mt-2 grid gap-2 sm:grid-cols-2">
      {providers.map((p) => (
        <div
          key={p.id}
          className={`rounded-lg border p-2.5 text-xs ${
            p.active ? "border-accent bg-accent-soft" : "border-border"
          }`}
        >
          <div className="flex items-center justify-between gap-2">
            <span className="font-semibold">{p.label}</span>
            <span className={p.has_key ? "text-accent" : "text-muted"}>
              {p.has_key ? "key set" : `no ${p.api_key_env[0]}`}
            </span>
          </div>
          <p className="mt-1 text-muted">
            {p.vision ? "reads images" : "no image support"}
            {" · "}
            {p.structured_output === "schema" ? "enforces schemas" : "JSON only, schema not enforced"}
          </p>
          <p className="mt-0.5 text-muted">default: {p.default_model}</p>
        </div>
      ))}
    </div>
  );
}

export default function SystemPage() {
  const [settings, setSettings] = useState<Setting[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [jobs, setJobs] = useState<ModificationJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<{ text: string; kind?: "error" | "success" }>({ text: "" });

  const [prompt, setPrompt] = useState("");
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState<JobKind>("skill");
  const [submitting, setSubmitting] = useState(false);

  const refresh = useCallback(async () => {
    const [settingsRes, statusRes, jobsRes, providersRes] = await Promise.all([
      api.listSettings(),
      api.systemStatus(),
      api.listModifications(),
      api.listProviders(),
    ]);
    setSettings(settingsRes.settings);
    setStatus(statusRes);
    setJobs(jobsRes.jobs);
    setProviders(providersRes.providers);
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      try {
        await refresh();
      } catch {
        if (!cancelled) setMessage({ text: "Could not reach the backend.", kind: "error" });
      }
      if (!cancelled) setLoading(false);
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [refresh]);

  // A running job finishes on a background thread with nothing to push an
  // update, so poll while any job is in flight — and only while.
  const running = jobs.some((j) => j.status === "running");
  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => {
      refresh().catch(() => {});
    }, 2000);
    return () => clearInterval(id);
  }, [running, refresh]);

  async function saveSetting(key: string, value: boolean | number | string) {
    setSettings((prev) => prev.map((s) => (s.key === key ? { ...s, value } : s)));
    try {
      const res = await api.updateSettings({ [key]: value });
      setSettings(res.settings);
      const [statusRes, providersRes] = await Promise.all([api.systemStatus(), api.listProviders()]);
      setStatus(statusRes);
      setProviders(providersRes.providers);
      setMessage({ text: "Saved.", kind: "success" });
    } catch (err) {
      setMessage({ text: err instanceof ApiError ? err.message : "Could not save.", kind: "error" });
      await refresh().catch(() => {});
    }
  }

  async function submitRequest() {
    if (!prompt.trim()) return setMessage({ text: "Describe the change first.", kind: "error" });
    setSubmitting(true);
    setMessage({ text: "" });
    try {
      const job = await api.createModification({ prompt, title, kind });
      setJobs((prev) => [job, ...prev]);
      setPrompt("");
      setTitle("");
      setMessage({
        text: job.status === "pending" ? "Saved as a pending job — run it when you're ready." : "Started.",
        kind: "success",
      });
    } catch (err) {
      setMessage({ text: err instanceof ApiError ? err.message : "Something went wrong.", kind: "error" });
    } finally {
      setSubmitting(false);
    }
  }

  function handleJobChange(updated: ModificationJob) {
    setJobs((prev) => prev.map((j) => (j.id === updated.id ? updated : j)));
  }

  const enabled = Boolean(settings.find((s) => s.key === "self_modification_enabled")?.value);
  const pending = jobs.filter((j) => j.status === "pending");
  const rest = jobs.filter((j) => j.status !== "pending");
  const modelSettings = settings.filter((s) => s.key.startsWith("llm_"));
  const selfModSettings = settings.filter((s) => !s.key.startsWith("llm_"));
  const active = providers.find((p) => p.active);

  if (loading) return <p className="text-sm text-muted">Loading...</p>;

  return (
    <div>
      <section className="mb-6 rounded-[10px] border border-border bg-surface p-4 shadow-sm">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Model</h2>
        <p className="mt-1.5 text-sm text-muted">
          Which API the assistant thinks with. Keys are read from <code>.env</code> only — they are never
          stored here or sent back to this page.
        </p>
        {active && !active.has_key && (
          <p className="mt-1.5 text-sm text-danger">
            {active.label} is selected but no key is set. Add {active.api_key_env[0]} to .env and restart the
            backend.
          </p>
        )}
        <ProviderGrid providers={providers} />
        <div className="mt-2">
          {modelSettings.map((setting) => (
            <SettingRow key={setting.key} setting={setting} onChange={saveSetting} />
          ))}
        </div>
      </section>

      <section className="mb-6 rounded-[10px] border border-border bg-surface p-4 shadow-sm">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Self-modification</h2>
        <p className="mt-1.5 text-sm text-muted">
          {enabled
            ? "New requests run on their own, within the limits below."
            : "Requests are saved as pending jobs. Nothing runs until you run it."}
        </p>
        <div className="mt-2">
          {selfModSettings.map((setting) => (
            <SettingRow
              key={setting.key}
              setting={setting}
              onChange={saveSetting}
              // The sub-switches do nothing while the master switch is off.
              disabled={!enabled && setting.key.startsWith("self_modification_auto_")}
            />
          ))}
        </div>
        <StatusMessage text={message.text} kind={message.kind} />
      </section>

      {status && (status.code_preflight.length > 0 || !status.agent_available) && (
        <section className="mb-6 rounded-[10px] border border-border bg-surface p-4 text-sm shadow-sm">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Before code changes can run</h2>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-muted">
            {!status.agent_available && (
              <li>
                The coding agent command isn&apos;t on PATH. Set its full path in{" "}
                <span className="font-semibold">Coding agent command</span> above.
              </li>
            )}
            {status.code_preflight.map((problem) => (
              <li key={problem}>{problem}</li>
            ))}
          </ul>
        </section>
      )}

      <section className="mb-6 rounded-[10px] border border-border bg-surface p-4 shadow-sm">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Request a change</h2>
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          {(["skill", "code"] as JobKind[]).map((k) => (
            <button
              key={k}
              onClick={() => setKind(k)}
              className={`rounded-full border px-3.5 py-1.5 text-sm cursor-pointer ${
                kind === k ? "border-accent font-semibold text-accent" : "border-border text-muted"
              }`}
            >
              {k === "skill" ? "New skill" : "Code change"}
            </button>
          ))}
        </div>
        <p className="mt-2 text-xs text-muted">
          {kind === "skill"
            ? "Teaches it to recognize and extract a new kind of content. Writes a skill file — no code runs."
            : "Runs a coding agent against the source. Changes land on their own git branch and are never merged for you."}
        </p>
        <input
          className={`${textInput} mt-2.5`}
          placeholder="Short title (optional)"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <textarea
          className={`${textInput} mt-2`}
          rows={4}
          placeholder={
            kind === "skill"
              ? "e.g. Track my car servicing — which garage, what was done, when the next one is due."
              : "e.g. Let me edit an entry's title and summary after it's been saved."
          }
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
        />
        <button className={primaryBtn} onClick={submitRequest} disabled={submitting}>
          {submitting ? "Submitting..." : enabled ? "Submit" : "Save as pending"}
        </button>
      </section>

      {pending.length > 0 && (
        <section className="mb-6">
          <h2 className="mb-2.5 text-sm font-semibold uppercase tracking-wide text-muted">
            Waiting for you ({pending.length})
          </h2>
          <div className="flex flex-col gap-2.5">
            {pending.map((job) => (
              <JobCard key={job.id} job={job} onChange={handleJobChange} />
            ))}
          </div>
        </section>
      )}

      {rest.length > 0 && (
        <section>
          <h2 className="mb-2.5 text-sm font-semibold uppercase tracking-wide text-muted">History</h2>
          <div className="flex flex-col gap-2.5">
            {rest.map((job) => (
              <JobCard key={job.id} job={job} onChange={handleJobChange} />
            ))}
          </div>
        </section>
      )}

      {jobs.length === 0 && (
        <p className="text-sm text-muted">
          No modification requests yet. Ask for one above, or just save a note saying what the assistant
          should be able to do — it files the request itself.
        </p>
      )}
    </div>
  );
}
