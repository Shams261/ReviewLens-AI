const API_BASE = import.meta.env.VITE_API_URL || "/api";

export async function apiFetch<T>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || "API request failed");
  }
  return res.json();
}

// ---- Typed API functions ----

export interface IngestResponse {
  session_id: string;
  product_name: string;
  platform: string;
  review_count: number;
  source: string;
}

export interface KeywordData {
  word: string;
  count: number;
  avg_rating: number;
  mention_pct: number;
}

export interface SentimentData {
  positive: number;
  neutral: number;
  negative: number;
  positive_pct: number;
  neutral_pct: number;
  negative_pct: number;
}

export interface SummaryResponse {
  session_id: string;
  product_name: string;
  platform: string;
  total_reviews: number;
  average_rating: number;
  star_distribution: Record<string, number>;
  date_range: { earliest: string | null; latest: string | null };
  verified: { count: number; percentage: number };
  top_keywords: KeywordData[];
  sentiment: SentimentData;
}

export interface ChatMessageData {
  id: number;
  role: "user" | "assistant";
  content: string;
  scope_status: string;
  created_at: string | null;
}

export interface CitedReview {
  id: number;
  rating: number;
  title: string | null;
  body: string;
  author: string | null;
  date: string | null;
  verified: boolean;
  helpful_votes: number;
}

export interface ChatResponse {
  reply: string;
  scope_status: string;
  source: string;
  model: string;
  cited_reviews: CitedReview[];
  cached: boolean;
  confidence: number;
}

export function ingestUrl(url: string) {
  return apiFetch<IngestResponse>("/ingest/url", {
    method: "POST",
    body: JSON.stringify({ url }),
  });
}

export interface IngestProgressEvent {
  type: "progress";
  page: number;
  reviews_found: number;
  max_pages: number;
  message?: string;
}

export interface IngestDoneEvent extends IngestResponse {
  type: "done";
  asin: string;
}

export interface IngestErrorEvent {
  type: "error";
  detail: string;
}

export type IngestSSEEvent = IngestProgressEvent | IngestDoneEvent | IngestErrorEvent;

/**
 * Ingest URL with SSE progress streaming.
 */
export async function ingestUrlStream(
  url: string,
  onEvent: (event: IngestSSEEvent) => void,
): Promise<void> {
  const res = await fetch(`${API_BASE}/ingest/url/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Stream request failed");
  }

  const reader = res.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.startsWith("data: ")) {
        try {
          const event: IngestSSEEvent = JSON.parse(trimmed.slice(6));
          onEvent(event);
        } catch {
          // skip malformed
        }
      }
    }
  }

  if (buffer.trim().startsWith("data: ")) {
    try {
      onEvent(JSON.parse(buffer.trim().slice(6)));
    } catch { /* skip */ }
  }
}

export function loadDemo() {
  return apiFetch<IngestResponse>("/ingest/demo", { method: "POST" });
}

export function uploadCSV(file: File, productName: string) {
  const form = new FormData();
  form.append("file", file);
  form.append("product_name", productName);
  return fetch(`${API_BASE}/ingest/csv`, { method: "POST", body: form }).then(
    async (res) => {
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || "Upload failed");
      }
      return res.json() as Promise<IngestResponse>;
    }
  );
}

export function fetchSummary(sessionId: string) {
  return apiFetch<SummaryResponse>(`/reviews/summary?session_id=${sessionId}`);
}

export interface ReviewItem {
  id: number;
  rating: number;
  title: string | null;
  body: string;
  author: string | null;
  date: string | null;
  verified: boolean;
  helpful_votes: number;
}

export interface ReviewsPage {
  reviews: ReviewItem[];
  total: number;
  page: number;
  limit: number;
  pages: number;
}

export function fetchReviews(sessionId: string, page = 1, limit = 15) {
  return apiFetch<ReviewsPage>(`/reviews/?session_id=${sessionId}&page=${page}&limit=${limit}`);
}

export function sendChat(sessionId: string, query: string) {
  return apiFetch<ChatResponse>("/chat/", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, query }),
  });
}

export function fetchChatHistory(sessionId: string) {
  return apiFetch<{ session_id: string; messages: ChatMessageData[] }>(
    `/chat/history?session_id=${sessionId}`
  );
}

// ---- SSE Streaming Chat ----

export interface SSEMetaEvent {
  type: "meta";
  reply: string;
  scope_status: string;
  source: string;
  model: string;
  cited_reviews: CitedReview[];
  cached: boolean;
  confidence: number;
}

export interface SSETokenEvent {
  type: "token";
  content: string;
}

export interface SSEDoneEvent {
  type: "done";
  reply?: string;
  scope_status: string;
  source: string;
  model: string;
  cited_reviews: CitedReview[];
  cached: boolean;
  confidence: number;
  replaced?: boolean;
}

export interface SSEErrorEvent {
  type: "error";
  detail: string;
}

export type SSEEvent = SSEMetaEvent | SSETokenEvent | SSEDoneEvent | SSEErrorEvent;

/**
 * Stream chat response via SSE. Calls onEvent for each parsed event.
 * Returns when the stream ends.
 */
export async function sendChatStream(
  sessionId: string,
  query: string,
  onEvent: (event: SSEEvent) => void,
): Promise<void> {
  const res = await fetch(`${API_BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, query }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Stream request failed");
  }

  const reader = res.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // Parse SSE lines: "data: {...}\n\n"
    const lines = buffer.split("\n");
    buffer = lines.pop() || ""; // keep incomplete line in buffer

    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.startsWith("data: ")) {
        try {
          const event: SSEEvent = JSON.parse(trimmed.slice(6));
          onEvent(event);
        } catch {
          // skip malformed events
        }
      }
    }
  }

  // Process any remaining buffer
  if (buffer.trim().startsWith("data: ")) {
    try {
      const event: SSEEvent = JSON.parse(buffer.trim().slice(6));
      onEvent(event);
    } catch {
      // skip
    }
  }
}
