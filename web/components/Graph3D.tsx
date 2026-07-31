"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import ForceGraph3D, { ForceGraphMethods } from "react-force-graph-3d";
import type { GraphData, GraphLink, GraphNode } from "@/lib/types";

// Validated categorical palette (dark-surface steps), fixed order -- never
// cycled per-render. 9th+ distinct category folds into OVERFLOW_COLOR rather
// than generating a new hue.
const CATEGORY_COLORS = [
  "#3987e5", // blue
  "#d95926", // orange
  "#199e70", // aqua
  "#c98500", // yellow
  "#d55181", // magenta
  "#008300", // green
  "#9085e9", // violet
  "#e66767", // red
];
const TAG_COLOR = "#c3c2b7";
const OVERFLOW_COLOR = "#57534a";
const BACKGROUND = "#1a1815";

function escapeHtml(text: string): string {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function endpointId(end: GraphLink["source"] | GraphLink["target"]): string {
  return typeof end === "string" ? end : (end as unknown as GraphNode).id;
}

export default function Graph3D({ data }: { data: GraphData }) {
  const router = useRouter();
  const containerRef = useRef<HTMLDivElement>(null);
  const fgRef = useRef<ForceGraphMethods<GraphNode, GraphLink> | undefined>(undefined);
  const [size, setSize] = useState({ width: 800, height: 600 });
  const [focusId, setFocusId] = useState<string | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) setSize({ width: entry.contentRect.width, height: Math.max(500, entry.contentRect.height) });
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const timeout = setTimeout(() => fgRef.current?.zoomToFit(600, 60), 400);
    return () => clearTimeout(timeout);
  }, [data]);

  const colorByCategory = useMemo(() => {
    const categories: string[] = [];
    for (const node of data.nodes) {
      if (node.type === "entry" && !categories.includes(node.group)) categories.push(node.group);
    }
    const map = new Map<string, string>();
    categories.forEach((cat, i) => map.set(cat, CATEGORY_COLORS[i] ?? OVERFLOW_COLOR));
    return map;
  }, [data.nodes]);

  const neighbors = useMemo(() => {
    if (!focusId) return null;
    const set = new Set<string>([focusId]);
    for (const link of data.links) {
      const s = endpointId(link.source);
      const t = endpointId(link.target);
      if (s === focusId) set.add(t);
      if (t === focusId) set.add(s);
    }
    return set;
  }, [focusId, data.links]);

  function baseNodeColor(node: GraphNode): string {
    return node.type === "tag" ? TAG_COLOR : colorByCategory.get(node.group) ?? OVERFLOW_COLOR;
  }

  function nodeColor(node: GraphNode): string {
    if (neighbors && !neighbors.has(node.id)) return "rgba(120,116,105,0.12)";
    return baseNodeColor(node);
  }

  function linkColor(link: GraphLink): string {
    const dimmed = neighbors ? !(neighbors.has(endpointId(link.source)) && neighbors.has(endpointId(link.target))) : false;
    if (link.type === "tag") return dimmed ? "rgba(195,194,183,0.03)" : "rgba(195,194,183,0.3)";
    const alpha = Math.min(0.75, 0.25 + link.value * 0.4);
    return dimmed ? "rgba(226,148,106,0.03)" : `rgba(226,148,106,${alpha})`;
  }

  function handleNodeClick(node: GraphNode) {
    if (node.type === "tag") {
      setFocusId((prev) => (prev === node.id ? null : node.id));
      return;
    }
    if (node.entryId) router.push(`/library/${node.entryId}`);
  }

  return (
    <div ref={containerRef} className="relative h-[70vh] min-h-[500px] w-full overflow-hidden rounded-[10px] border border-border">
      <ForceGraph3D<GraphNode, GraphLink>
        ref={fgRef}
        graphData={data}
        width={size.width}
        height={size.height}
        backgroundColor={BACKGROUND}
        nodeLabel={(node) => escapeHtml(node.type === "tag" ? `# ${node.label}` : node.label)}
        nodeVal={(node) => node.val}
        nodeColor={nodeColor}
        nodeOpacity={0.95}
        nodeResolution={12}
        linkColor={linkColor}
        linkWidth={(link) => (link.type === "similar" ? Math.max(0.6, link.value * 3) : 0.6)}
        linkOpacity={0.6}
        onNodeClick={handleNodeClick}
        onBackgroundClick={() => setFocusId(null)}
        enableNodeDrag={false}
        showNavInfo={false}
      />
      {focusId && (
        <button
          onClick={() => setFocusId(null)}
          className="absolute right-3 top-3 rounded-full border border-border bg-surface/90 px-3 py-1.5 text-xs text-foreground"
        >
          Clear focus &times;
        </button>
      )}
    </div>
  );
}
