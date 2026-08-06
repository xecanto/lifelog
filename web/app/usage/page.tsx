"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { UsageResponse } from "@/lib/types";
import SubNav from "@/components/SubNav";
import { MANAGE_TABS } from "@/lib/nav";
import { BreakdownBars, SpendChart, TokenSplit, type SpendPoint } from "@/components/charts";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  PageHeader,
  Section,
  Skeleton,
  StatGrid,
  StatTile,
} from "@/components/ui";
import { formatCount, formatDuration, formatTimestamp, formatUsd, titleCase } from "@/lib/format";

const WINDOWS = [7, 30, 90];

/**
 * Fill the gaps in the daily series.
 *
 * The API returns only days that had calls. Plotting those alone would space
 * an idle week the same as a busy one, so the quiet days are added back as
 * zeroes before anything is drawn.
 */
function toDailySeries(usage: UsageResponse): SpendPoint[] {
  const byDay = new Map(usage.daily.map((d) => [d.day, d]));
  const series: SpendPoint[] = [];
  const cursor = new Date();
  cursor.setDate(cursor.getDate() - (usage.days - 1));

  for (let i = 0; i < usage.days; i++) {
    const key = cursor.toISOString().slice(0, 10);
    const row = byDay.get(key);
    series.push({ day: key, cost: row?.cost_usd ?? 0, calls: row?.calls ?? 0 });
    cursor.setDate(cursor.getDate() + 1);
  }
  return series;
}

export default function UsagePage() {
  const [usage, setUsage] = useState<UsageResponse | null>(null);
  const [days, setDays] = useState(30);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      try {
        const res = await api.usage(days);
        if (!cancelled) setUsage(res);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Something went wrong.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [days]);

  const series = useMemo(() => (usage ? toDailySeries(usage) : []), [usage]);

  return (
    <>
      <SubNav tabs={MANAGE_TABS} />
      <PageHeader
        title="Usage"
        description="What the assistant has spent on model calls, and which parts of it are spending."
        actions={
          <div className="inline-flex rounded-lg border border-border bg-surface-sunken p-1">
            {WINDOWS.map((option) => (
              <button
                key={option}
                onClick={() => setDays(option)}
                className={`cursor-pointer rounded-md px-3 py-1.5 text-sm font-medium transition ${
                  days === option ? "bg-surface text-foreground shadow-soft" : "text-muted hover:text-foreground"
                }`}
              >
                {option}d
              </button>
            ))}
          </div>
        }
      />

      {error && (
        <Card className="mb-6 border-danger text-sm text-danger">
          Couldn&apos;t load usage: {error}
        </Card>
      )}

      {loading && !usage && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-24" />
            ))}
          </div>
          <Skeleton className="h-64" />
        </div>
      )}

      {usage && usage.all_time.calls === 0 && (
        <EmptyState
          icon="📊"
          title="No model calls yet"
          description="Capture something or ask a question, and every call the assistant makes will be metered here — tokens, latency, and cost."
          action={
            <a href="/add" className="inline-flex">
              <Button>Capture something</Button>
            </a>
          }
        />
      )}

      {usage && usage.all_time.calls > 0 && (
        <>
          <StatGrid>
            <StatTile
              label={`Spend · ${days}d`}
              value={formatUsd(usage.window.cost_usd)}
              hint={`${formatUsd(usage.all_time.cost_usd)} all time`}
            />
            <StatTile
              label="Calls"
              value={usage.window.calls.toLocaleString()}
              hint={
                usage.window.failed > 0
                  ? `${usage.window.failed} failed`
                  : `${usage.all_time.calls.toLocaleString()} all time`
              }
              tone={usage.window.failed > 0 ? "danger" : undefined}
            />
            <StatTile
              label="Tokens"
              value={formatCount(usage.window.input_tokens + usage.window.output_tokens)}
              hint={`${formatCount(usage.window.cache_read_tokens)} from cache`}
            />
            <StatTile
              label="Avg per call"
              value={
                usage.window.calls
                  ? formatUsd(usage.window.cost_usd / usage.window.calls)
                  : formatUsd(0)
              }
              hint={`over ${days} days`}
            />
          </StatGrid>

          {usage.window.unpriced > 0 && (
            <p className="mt-3 text-xs text-muted">
              {usage.window.unpriced} call{usage.window.unpriced === 1 ? "" : "s"} used a model with no
              published rate on file, so they count toward tokens but not toward spend. Set{" "}
              <code className="rounded bg-surface-sunken px-1 py-0.5">LIFELOG_PRICE_&lt;MODEL&gt;</code> to
              include them.
            </p>
          )}

          <Section title="Spend over time" description={`Daily cost across the last ${days} days.`}>
            <Card>
              <SpendChart points={series} />
            </Card>
          </Section>

          <div className="grid gap-4 sm:grid-cols-2">
            <Section title="By feature" description="Which part of the app is spending.">
              <Card>
                <BreakdownBars
                  rows={usage.by_operation.map((row) => ({
                    name: titleCase(row.name),
                    cost: row.cost_usd,
                    calls: row.calls,
                    tokens: row.input_tokens + row.output_tokens,
                  }))}
                />
              </Card>
            </Section>

            <Section title="By model" description="Where the money goes per model.">
              <Card>
                <BreakdownBars
                  rows={usage.by_model.map((row) => ({
                    name: row.name,
                    cost: row.cost_usd,
                    calls: row.calls,
                    tokens: row.input_tokens + row.output_tokens,
                  }))}
                />
              </Card>
            </Section>
          </div>

          <Section
            title="Token mix"
            description="Output tokens cost several times what input tokens do, so the split is where the bill actually comes from."
          >
            <Card>
              <TokenSplit
                input={usage.window.input_tokens}
                output={usage.window.output_tokens}
              />
            </Card>
          </Section>

          <Section title="Recent calls">
            <Card padded={false}>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-xs tracking-wide text-muted uppercase">
                      <th className="px-4 py-3 font-medium">When</th>
                      <th className="px-4 py-3 font-medium">Feature</th>
                      <th className="px-4 py-3 font-medium">Model</th>
                      <th className="px-4 py-3 text-right font-medium">Tokens</th>
                      <th className="px-4 py-3 text-right font-medium">Time</th>
                      <th className="px-4 py-3 text-right font-medium">Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {usage.recent.map((call) => (
                      <tr key={call.id} className="border-b border-border last:border-0">
                        <td className="tabular px-4 py-3 whitespace-nowrap text-muted">
                          {formatTimestamp(call.created_at)}
                        </td>
                        <td className="px-4 py-3">
                          {call.ok ? (
                            titleCase(call.operation)
                          ) : (
                            <span className="flex items-center gap-2">
                              {titleCase(call.operation)}
                              <Badge tone="danger">Failed</Badge>
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-muted">{call.model}</td>
                        <td className="tabular px-4 py-3 text-right text-muted">
                          {formatCount(call.input_tokens + call.output_tokens)}
                        </td>
                        <td className="tabular px-4 py-3 text-right text-muted">
                          {formatDuration(call.duration_ms)}
                        </td>
                        <td className="tabular px-4 py-3 text-right">
                          {call.cost_usd === null ? (
                            <span className="text-subtle">—</span>
                          ) : (
                            formatUsd(call.cost_usd)
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </Section>
        </>
      )}
    </>
  );
}
