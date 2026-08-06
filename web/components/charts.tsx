"use client";

import { useEffect, useRef, useState } from "react";
import { formatCount, formatUsd } from "@/lib/format";

/**
 * Charts for the usage page.
 *
 * Both forms are single-series: spend over time is one quantity, and the
 * breakdowns compare magnitudes within one measure. A single series needs no
 * legend -- the heading names what's plotted -- and one hue, not one hue per
 * bar, which would imply a category difference that isn't there.
 *
 * Colours come from --chart-1, defined per theme in globals.css and validated
 * for colour-vision deficiency and contrast against both surfaces.
 */

/** Width of the element, tracked so SVG text renders at its real size. */
function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return [ref, width] as const;
}

/**
 * Axis ticks, all at the same precision.
 *
 * `formatUsd` varies its decimals with magnitude, which is right for a single
 * figure but wrong down an axis: a scale topping out at $1 would read
 * "$0.00 / $0.500 / $1.00". The precision is picked once, from the largest
 * tick, and every tick wears it.
 */
function axisTicks(max: number): { value: number; label: string }[] {
  const decimals = max >= 1 ? 2 : max >= 0.1 ? 3 : 4;
  return [0, max / 2, max].map((value) => ({
    value,
    label: `$${value.toFixed(decimals)}`,
  }));
}

function niceCeiling(value: number): number {
  if (value <= 0) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const normalized = value / magnitude;
  const step = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
  return step * magnitude;
}

export type SpendPoint = { day: string; cost: number; calls: number };

/**
 * Spend per day: 2px line over a 10% wash, with a crosshair on hover.
 *
 * Days with no calls are plotted as zero rather than skipped -- a gap would
 * read as missing data when it actually means "you didn't use it that day".
 */
export function SpendChart({ points }: { points: SpendPoint[] }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);

  const height = 200;
  const pad = { top: 16, right: 16, bottom: 28, left: 52 };
  const plotW = Math.max(width - pad.left - pad.right, 10);
  const plotH = height - pad.top - pad.bottom;

  const max = niceCeiling(Math.max(...points.map((p) => p.cost), 0));
  const x = (i: number) => pad.left + (points.length === 1 ? plotW / 2 : (i / (points.length - 1)) * plotW);
  const y = (v: number) => pad.top + plotH - (v / max) * plotH;

  const line = points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i)},${y(p.cost)}`).join(" ");
  const area = points.length
    ? `${line} L${x(points.length - 1)},${pad.top + plotH} L${x(0)},${pad.top + plotH} Z`
    : "";

  const ticks = axisTicks(max);
  const active = hover !== null ? points[hover] : null;

  return (
    <div ref={ref} className="relative">
      {width > 0 && (
        <svg
          width={width}
          height={height}
          role="img"
          aria-label={`Daily spend over ${points.length} days`}
          onMouseLeave={() => setHover(null)}
          onMouseMove={(event) => {
            const bounds = event.currentTarget.getBoundingClientRect();
            const offset = event.clientX - bounds.left - pad.left;
            const index = Math.round((offset / plotW) * (points.length - 1));
            setHover(Math.max(0, Math.min(points.length - 1, index)));
          }}
        >
          {/* Gridlines and their ticks: hairline, solid, one step off surface. */}
          {ticks.map((tick) => (
            <g key={tick.value}>
              <line
                x1={pad.left}
                x2={pad.left + plotW}
                y1={y(tick.value)}
                y2={y(tick.value)}
                stroke="var(--chart-grid)"
                strokeWidth={1}
              />
              <text
                x={pad.left - 8}
                y={y(tick.value) + 4}
                textAnchor="end"
                fontSize={11}
                fill="var(--subtle)"
                style={{ fontVariantNumeric: "tabular-nums" }}
              >
                {tick.label}
              </text>
            </g>
          ))}

          <path d={area} fill="var(--chart-1)" opacity={0.1} />
          <path
            d={line}
            fill="none"
            stroke="var(--chart-1)"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
          />

          {/* First and last day only -- a tick per day would be unreadable. */}
          {points.length > 1 &&
            [0, points.length - 1].map((i) => (
              <text
                key={i}
                x={x(i)}
                y={height - 8}
                textAnchor={i === 0 ? "start" : "end"}
                fontSize={11}
                fill="var(--subtle)"
              >
                {points[i].day.slice(5)}
              </text>
            ))}

          {hover !== null && (
            <g>
              <line
                x1={x(hover)}
                x2={x(hover)}
                y1={pad.top}
                y2={pad.top + plotH}
                stroke="var(--chart-axis)"
                strokeWidth={1}
              />
              {/* 2px surface ring keeps the dot legible over the line. */}
              <circle
                cx={x(hover)}
                cy={y(points[hover].cost)}
                r={5}
                fill="var(--chart-1)"
                stroke="var(--surface)"
                strokeWidth={2}
              />
            </g>
          )}
        </svg>
      )}

      {active && (
        <div
          className="pointer-events-none absolute top-0 rounded-md border border-border bg-surface px-3 py-2 text-xs shadow-float"
          style={{
            left: Math.min(Math.max(x(hover!) - 60, 0), Math.max(width - 130, 0)),
          }}
        >
          <div className="font-medium">{active.day}</div>
          <div className="tabular mt-0.5 text-muted">
            {formatUsd(active.cost)} · {active.calls} {active.calls === 1 ? "call" : "calls"}
          </div>
        </div>
      )}
    </div>
  );
}

export type BreakdownRow = { name: string; cost: number; calls: number; tokens: number };

/**
 * Ranked horizontal bars. Bars are capped at 20px so the row's leftover height
 * stays as air, and the value rides the tip rather than sitting inside, where
 * a short bar would clip it.
 */
export function BreakdownBars({
  rows,
  empty = "Nothing recorded yet.",
}: {
  rows: BreakdownRow[];
  empty?: string;
}) {
  if (!rows.length) {
    return <p className="py-6 text-center text-sm text-muted">{empty}</p>;
  }

  const max = Math.max(...rows.map((r) => r.cost), 0.0000001);

  return (
    <ul className="space-y-3">
      {rows.map((row) => (
        <li key={row.name}>
          <div className="mb-1.5 flex items-baseline justify-between gap-3 text-sm">
            <span className="truncate font-medium">{row.name}</span>
            <span className="tabular shrink-0 text-muted">
              {formatUsd(row.cost)}
              <span className="ml-2 text-subtle">
                {row.calls} · {formatCount(row.tokens)} tok
              </span>
            </span>
          </div>
          <div className="h-2.5 overflow-hidden rounded-sm bg-surface-sunken">
            <div
              className="h-full rounded-r-sm"
              style={{
                width: `${Math.max((row.cost / max) * 100, 1.5)}%`,
                background: "var(--chart-1)",
              }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}

/**
 * Input vs output tokens as one split bar. Two series, so it carries a legend
 * and a 2px surface gap between the segments.
 */
export function TokenSplit({ input, output }: { input: number; output: number }) {
  const total = input + output;
  if (!total) return null;
  const inputPct = (input / total) * 100;

  return (
    <div>
      <div className="flex h-3 overflow-hidden rounded-sm bg-surface-sunken">
        <div style={{ width: `${inputPct}%`, background: "var(--chart-1)" }} />
        <div style={{ width: "2px", background: "var(--surface)" }} />
        <div style={{ flex: 1, background: "var(--chart-2)" }} />
      </div>
      <div className="mt-2.5 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted">
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: "var(--chart-1)" }} />
          Input <span className="tabular text-foreground">{formatCount(input)}</span>
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: "var(--chart-2)" }} />
          Output <span className="tabular text-foreground">{formatCount(output)}</span>
        </span>
      </div>
    </div>
  );
}
