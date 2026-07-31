"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { GraphData } from "@/lib/types";

// three.js needs the browser -- never render on the server, and only pull
// its (large) JS into the bundle when someone actually opens this page.
const Graph3D = dynamic(() => import("@/components/Graph3D"), {
  ssr: false,
  loading: () => <p className="text-sm text-muted">Loading 3D graph...</p>,
});

export default function GraphLoader() {
  const [data, setData] = useState<GraphData | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .graph()
      .then(setData)
      .catch(() => setError("Could not load the graph. Is the backend running?"));
  }, []);

  if (error) return <p className="text-sm text-danger">{error}</p>;
  if (!data) return <p className="text-sm text-muted">Loading graph data...</p>;
  if (data.nodes.length === 0) {
    return <p className="text-sm text-muted">Nothing to graph yet — save a few entries first.</p>;
  }

  return (
    <div>
      <p className="mb-3 text-sm text-muted">
        Drag to rotate, scroll to zoom. Click a topic (light node) to see everything connected to it; click an entry
        (colored node) to open it.
      </p>
      <Graph3D data={data} />
    </div>
  );
}
