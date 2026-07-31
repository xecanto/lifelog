import GraphLoader from "@/components/GraphLoader";

export default function GraphPage() {
  return (
    <div>
      <h1 className="mb-1 text-lg font-bold">Knowledge graph</h1>
      <GraphLoader />
    </div>
  );
}
