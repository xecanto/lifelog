export type SourceType = "text" | "file" | "link" | "image" | "voice";

export type FacetStatus = "open" | "done" | "dismissed";

/** One thing a capture is about. A single note can produce several. */
export interface Facet {
  id: number;
  entry_id: number;
  created_at: string;
  /** The skill that produced this facet, e.g. "subscription". */
  kind: string;
  label: string;
  /** The skill's full extraction, shape varies by kind. */
  data: Record<string, unknown>;
  due_at: string | null;
  cadence: string | null;
  amount: number | null;
  currency: string | null;
  identity: string | null;
  vendor: string | null;
  status: FacetStatus;
  /** Present when the facet is fetched on its own, not via an entry. */
  entry_title?: string;
  entry_category?: string;
  entry_source_type?: SourceType;
}

export interface Entry {
  id: number;
  created_at: string;
  source_type: SourceType;
  title: string;
  raw_text: string;
  summary: string;
  category: string;
  tags: string[];
  skill: string;
  source_url: string | null;
  file_path: string | null;
  original_filename: string | null;
  metadata: Record<string, unknown>;
  facets: Facet[];
}

export interface Agenda {
  today: string;
  window_days: number;
  overdue: Facet[];
  due_today: Facet[];
  upcoming: Facet[];
  counts: { overdue: number; due_today: number; upcoming: number };
}

export interface SpendSummary {
  monthly_by_currency: Record<string, number>;
  counted: number;
  unpriced: number;
}

export interface FacetListResponse {
  facets: Facet[];
  spend: SpendSummary;
}

export interface FacetKind {
  kind: string;
  count: number;
  open_count: number;
}

export interface EntryListResponse {
  entries: Entry[];
  total: number;
}

export interface CategoryCount {
  category: string;
  count: number;
}

export interface Skill {
  id: string;
  description: string;
  applies_to: SourceType[];
  fields: string[];
}

export interface AskResponse {
  answer: string;
  sources: Entry[];
}

export interface GraphNode {
  id: string;
  label: string;
  type: "entry" | "tag";
  group: string;
  val: number;
  entryId?: number;
  sourceType?: SourceType;
}

export interface GraphLink {
  source: string;
  target: string;
  type: "tag" | "similar";
  value: number;
}

export interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}
