import type {
  Agenda,
  AskResponse,
  CategoryCount,
  Entry,
  EntryListResponse,
  Facet,
  FacetKind,
  FacetListResponse,
  FacetStatus,
  GraphData,
  Skill,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export class ApiError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: init?.body instanceof FormData ? init.headers : { "Content-Type": "application/json", ...init?.headers },
    cache: "no-store",
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new ApiError(data.detail || `Request failed (${res.status})`);
  }
  return data as T;
}

export function mediaUrl(filePath: string): string {
  return `${API_URL}/media/${filePath.replace(/^storage\//, "")}`;
}

export const api = {
  addText: (text: string) => request<Entry>("/api/entries/text", { method: "POST", body: JSON.stringify({ text }) }),

  addLink: (url: string) => request<Entry>("/api/entries/link", { method: "POST", body: JSON.stringify({ url }) }),

  addFile: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<Entry>("/api/entries/file", { method: "POST", body: form });
  },

  addImage: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<Entry>("/api/entries/image", { method: "POST", body: form });
  },

  addVoice: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<Entry>("/api/entries/voice", { method: "POST", body: form });
  },

  listEntries: (params: { limit?: number; offset?: number; category?: string } = {}) => {
    const search = new URLSearchParams();
    if (params.limit) search.set("limit", String(params.limit));
    if (params.offset) search.set("offset", String(params.offset));
    if (params.category) search.set("category", params.category);
    return request<EntryListResponse>(`/api/entries?${search}`);
  },

  getEntry: (id: number | string) => request<Entry>(`/api/entries/${id}`),

  deleteEntry: (id: number | string) => request<{ ok: boolean }>(`/api/entries/${id}`, { method: "DELETE" }),

  listCategories: () => request<{ categories: CategoryCount[] }>("/api/categories"),

  listSkills: () => request<{ skills: Skill[] }>("/api/skills"),

  agenda: (days?: number) => request<Agenda>(`/api/agenda${days ? `?days=${days}` : ""}`),

  listFacets: (params: { kind?: string; status?: FacetStatus } = {}) => {
    const search = new URLSearchParams();
    if (params.kind) search.set("kind", params.kind);
    if (params.status) search.set("status", params.status);
    return request<FacetListResponse>(`/api/facets?${search}`);
  },

  listFacetKinds: () => request<{ kinds: FacetKind[] }>("/api/facet-kinds"),

  setFacetStatus: (id: number, status: FacetStatus) =>
    request<Facet>(`/api/facets/${id}`, { method: "PATCH", body: JSON.stringify({ status }) }),

  ask: (question: string) => request<AskResponse>("/api/ask", { method: "POST", body: JSON.stringify({ question }) }),

  graph: () => request<GraphData>("/api/graph"),
};
