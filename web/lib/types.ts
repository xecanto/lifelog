export type SourceType = "text" | "file" | "link" | "image" | "voice";

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
