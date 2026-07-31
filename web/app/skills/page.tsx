"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Skill } from "@/lib/types";

export default function SkillsPage() {
  const [skills, setSkills] = useState<Skill[] | null>(null);

  useEffect(() => {
    api.listSkills().then((res) => setSkills(res.skills));
  }, []);

  return (
    <div>
      <h1 className="text-lg font-bold">Skills</h1>
      <p className="mt-1 text-sm text-muted">
        Every entry is routed to one of these before it&apos;s organized. Nothing here is hardcoded — add a markdown file
        to the backend&apos;s <code className="rounded bg-accent-soft px-1 py-0.5 text-accent">skills/</code>{" "}
        directory and it shows up here immediately, with no restart.
      </p>

      {!skills ? (
        <p className="mt-4 text-sm text-muted">Loading...</p>
      ) : (
        <div className="mt-5 flex flex-col gap-2.5">
          {skills.map((skill) => (
            <div key={skill.id} className="rounded-[10px] border border-border bg-surface p-4">
              <div className="flex items-center justify-between gap-3">
                <span className="font-semibold">{skill.id}</span>
                <div className="flex flex-wrap justify-end gap-1.5">
                  {skill.applies_to.map((t) => (
                    <span key={t} className="rounded-full border border-border px-2 py-0.5 text-xs text-muted">
                      {t}
                    </span>
                  ))}
                </div>
              </div>
              <p className="mt-1.5 text-sm text-muted">{skill.description}</p>
              {skill.fields.length > 0 && (
                <p className="mt-2 text-xs text-muted">
                  Extra fields:{" "}
                  {skill.fields.map((f) => (
                    <span key={f} className="mr-1.5 rounded-full bg-accent-soft px-2 py-0.5 font-semibold text-accent">
                      {f}
                    </span>
                  ))}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
