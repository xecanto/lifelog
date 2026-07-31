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

export type JobKind = "skill" | "code";
export type JobStatus = "pending" | "running" | "succeeded" | "failed" | "cancelled";

/** A request to change the app itself. */
export interface ModificationJob {
  id: number;
  created_at: string;
  updated_at: string;
  title: string;
  prompt: string;
  kind: JobKind;
  status: JobStatus;
  /** "manual" when requested directly, "capture" when it came from a note. */
  origin: string;
  entry_id: number | null;
  branch: string | null;
  result: string;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface Setting {
  key: string;
  value: boolean | number | string;
  default: boolean | number | string;
  type: "bool" | "int" | "str";
  label: string;
  description: string;
  /** When present, the allowed values for this setting. */
  choices: string[] | null;
}

export interface Provider {
  id: string;
  label: string;
  default_model: string;
  suggested_models: string[];
  /** Env var names checked for this provider's key, in order. */
  api_key_env: string[];
  /** Whether a key is configured. The key itself is never sent. */
  has_key: boolean;
  structured_output: "schema" | "json_object" | "prompt";
  vision: boolean;
  active: boolean;
  base_url: string;
}

export interface ReflectionProposal {
  title: string;
  kind: JobKind;
  prompt: string;
  /** The evidence in the signals that justified this proposal. */
  why: string;
}

export interface ReflectionResult {
  ran: boolean;
  /** Why it didn't run, when `ran` is false. */
  reason: string;
  observations: string[];
  proposals: ReflectionProposal[];
  jobs: ModificationJob[];
}

export interface ActivityEvent {
  id: number;
  created_at: string;
  kind: string;
  entry_id: number | null;
  data: Record<string, unknown>;
}

export interface ProvidersResponse {
  providers: Provider[];
  active: { provider: string; model: string };
}

export interface SystemStatus {
  settings: Record<string, boolean | number | string>;
  counts: Record<string, number>;
  /** Reasons a code job can't run right now; empty means ready. */
  code_preflight: string[];
  agent_available: boolean;
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
