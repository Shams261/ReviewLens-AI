import { useEffect, useRef, useState } from "react";
import {
  sendChatStream,
  fetchChatHistory,
  fetchSummary,
  type CitedReview,
  type SSEEvent,
  type KeywordData,
} from "../lib/api";
import TypingDots from "./TypingDots";

interface Message {
  role: "user" | "assistant";
  content: string;
  scopeStatus: string;
  source?: string;
  model?: string;
  citedReviews?: CitedReview[];
  cached?: boolean;
  confidence?: number;
}

interface ChatInterfaceProps {
  sessionId: string;
  productName: string;
}

function buildSuggestedQuestions(productName: string, keywords: KeywordData[]): string[] {
  const generic = [
    "What are the top 3 complaints?",
    "What do verified purchasers say?",
    "What are the most praised features?",
    `Is ${productName} worth buying based on reviews?`,
  ];

  // Add keyword-based questions from the actual review data
  const keywordQuestions: string[] = [];
  const topWords = keywords.slice(0, 5).map((k) => k.word.toLowerCase());

  for (const word of topWords) {
    if (keywordQuestions.length >= 2) break;
    keywordQuestions.push(`What do reviewers say about the ${word}?`);
  }

  return [...generic, ...keywordQuestions];
}

// ---------------------------------------------------------------------------
// Simple Markdown → React renderer
// Handles: **bold**, _italic_, numbered lists, bullet lists, paragraphs.
// No external dependency needed.
// ---------------------------------------------------------------------------

function renderMarkdown(text: string): React.ReactNode[] {
  // Split into paragraphs / blocks
  const blocks = text.split(/\n{2,}/);
  const result: React.ReactNode[] = [];

  blocks.forEach((block, bi) => {
    const trimmed = block.trim();
    if (!trimmed) return;

    // Detect list blocks (lines starting with "- " or "N. ")
    const lines = trimmed.split("\n");
    const isBulletList = lines.every(
      (l) => /^\s*[-•]\s/.test(l) || l.trim() === ""
    );
    const isNumberedList = lines.every(
      (l) => /^\s*\d+\.\s/.test(l) || l.trim() === ""
    );

    if (isBulletList) {
      result.push(
        <ul key={bi} className="space-y-1.5 my-2">
          {lines
            .filter((l) => l.trim())
            .map((l, li) => (
              <li key={li} className="flex gap-2 items-start">
                <span className="text-blue-400 mt-1.5 shrink-0 text-[8px]">
                  ●
                </span>
                <span>{inlineMarkdown(l.replace(/^\s*[-•]\s*/, ""))}</span>
              </li>
            ))}
        </ul>
      );
    } else if (isNumberedList) {
      result.push(
        <ol key={bi} className="space-y-1.5 my-2">
          {lines
            .filter((l) => l.trim())
            .map((l, li) => {
              const match = l.match(/^\s*(\d+)\.\s*(.*)/);
              return (
                <li key={li} className="flex gap-2.5 items-start">
                  <span className="text-blue-500 font-bold text-xs min-w-[18px] text-right mt-0.5 shrink-0">
                    {match ? match[1] : li + 1}.
                  </span>
                  <span>
                    {inlineMarkdown(match ? match[2] : l)}
                  </span>
                </li>
              );
            })}
        </ol>
      );
    } else {
      // Regular paragraph — might contain single line breaks
      result.push(
        <p key={bi} className={bi > 0 ? "mt-2" : ""}>
          {lines.map((line, li) => (
            <span key={li}>
              {li > 0 && <br />}
              {inlineMarkdown(line)}
            </span>
          ))}
        </p>
      );
    }
  });

  return result;
}

/** Parse inline markdown: **bold**, _italic_ / *italic*, `code` */
function inlineMarkdown(text: string): React.ReactNode[] {
  // Pattern order matters: bold before italic
  const parts = text.split(
    /(\*\*[^*]+\*\*|__[^_]+__|_[^_]+_|\*[^*]+\*|`[^`]+`|\[Review\s*#\d+\])/g
  );
  return parts.map((part, i) => {
    if (/^\*\*(.+)\*\*$/.test(part) || /^__(.+)__$/.test(part)) {
      const inner = part.replace(/^\*\*|\*\*$|^__|__$/g, "");
      return (
        <strong key={i} className="font-semibold text-gray-900">
          {inner}
        </strong>
      );
    }
    if (/^_(.+)_$/.test(part) || /^\*([^*]+)\*$/.test(part)) {
      const inner = part.replace(/^_|_$|^\*|\*$/g, "");
      return (
        <em key={i} className="italic text-gray-500">
          {inner}
        </em>
      );
    }
    if (/^`(.+)`$/.test(part)) {
      const inner = part.replace(/^`|`$/g, "");
      return (
        <code
          key={i}
          className="bg-gray-100 text-blue-700 px-1.5 py-0.5 rounded text-xs font-mono"
        >
          {inner}
        </code>
      );
    }
    // [Review #N] citation badge is handled separately
    const citeMatch = part.match(/^\[Review\s*#(\d+)\]$/i);
    if (citeMatch) {
      // Return a placeholder — replaced in renderContent
      return <span key={i}>{part}</span>;
    }
    return <span key={i}>{part}</span>;
  });
}

// ---------------------------------------------------------------------------
// Content renderer — markdown + citation badges
// ---------------------------------------------------------------------------

function renderContent(
  text: string,
  citedReviews: CitedReview[],
  onCite: (id: number) => void
) {
  // First split by citation references
  const segments = text.split(/(\[Review\s*#\d+\])/gi);

  return segments.map((segment, i) => {
    const m = segment.match(/^\[Review\s*#(\d+)\]$/i);
    if (m) {
      const id = parseInt(m[1], 10);
      const exists = citedReviews.some((r) => r.id === id);
      return (
        <button
          key={`cite-${i}`}
          onClick={() => exists && onCite(id)}
          className={`inline-flex items-center gap-0.5 rounded-md px-1.5 py-0.5 text-[11px] font-semibold transition-all mx-0.5 ${
            exists
              ? "bg-blue-100 text-blue-700 hover:bg-blue-200 hover:shadow-sm cursor-pointer"
              : "bg-gray-100 text-gray-500 cursor-default"
          }`}
        >
          <svg viewBox="0 0 16 16" className="h-3 w-3" fill="currentColor">
            <path d="M1 3.5A1.5 1.5 0 012.5 2h11A1.5 1.5 0 0115 3.5v9a1.5 1.5 0 01-1.5 1.5h-11A1.5 1.5 0 011 12.5v-9zM2.5 3a.5.5 0 00-.5.5v9a.5.5 0 00.5.5h11a.5.5 0 00.5-.5v-9a.5.5 0 00-.5-.5h-11z" />
            <path d="M3 5.5a.5.5 0 01.5-.5h9a.5.5 0 010 1h-9a.5.5 0 01-.5-.5zM3 8a.5.5 0 01.5-.5h9a.5.5 0 010 1h-9A.5.5 0 013 8zm0 2.5a.5.5 0 01.5-.5h6a.5.5 0 010 1h-6a.5.5 0 01-.5-.5z" />
          </svg>
          #{m[1]}
        </button>
      );
    }
    // Render non-citation segments with markdown
    return <span key={`md-${i}`}>{renderMarkdown(segment)}</span>;
  });
}

// ---------------------------------------------------------------------------
// Source label helpers
// ---------------------------------------------------------------------------

interface SourceInfo {
  label: string;
  icon: React.ReactNode;
  color: string;
  bgColor: string;
  borderColor: string;
}

function getSourceInfo(message: Message): SourceInfo | null {
  if (message.role === "user") return null;
  if (message.scopeStatus === "out_of_scope") return null; // handled separately
  if (message.scopeStatus === "error") return null;

  const source = message.source;
  if (!source) return null;

  if (source === "deterministic") {
    return {
      label: "Data-Driven Analysis",
      icon: (
        <svg viewBox="0 0 20 20" className="h-3.5 w-3.5" fill="currentColor">
          <path d="M15.5 2A1.5 1.5 0 0014 3.5v13a1.5 1.5 0 001.5 1.5h1a1.5 1.5 0 001.5-1.5v-13A1.5 1.5 0 0016.5 2h-1zM9.5 6A1.5 1.5 0 008 7.5v9A1.5 1.5 0 009.5 18h1a1.5 1.5 0 001.5-1.5v-9A1.5 1.5 0 0010.5 6h-1zM3.5 10A1.5 1.5 0 002 11.5v5A1.5 1.5 0 003.5 18h1A1.5 1.5 0 006 16.5v-5A1.5 1.5 0 004.5 10h-1z" />
        </svg>
      ),
      color: "text-emerald-700",
      bgColor: "bg-emerald-50",
      borderColor: "border-emerald-200",
    };
  }

  if (source === "fallback") {
    return {
      label: "AI Unavailable — Data Summary",
      icon: (
        <svg viewBox="0 0 20 20" className="h-3.5 w-3.5" fill="currentColor">
          <path
            fillRule="evenodd"
            d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z"
            clipRule="evenodd"
          />
        </svg>
      ),
      color: "text-orange-700",
      bgColor: "bg-orange-50",
      borderColor: "border-orange-200",
    };
  }

  if (source === "cache") {
    return {
      label: "Cached Response",
      icon: (
        <svg viewBox="0 0 20 20" className="h-3.5 w-3.5" fill="currentColor">
          <path
            fillRule="evenodd"
            d="M10 18a8 8 0 100-16 8 8 0 000 16zm.75-13a.75.75 0 00-1.5 0v5c0 .414.336.75.75.75h4a.75.75 0 000-1.5h-3.25V5z"
            clipRule="evenodd"
          />
        </svg>
      ),
      color: "text-violet-700",
      bgColor: "bg-violet-50",
      borderColor: "border-violet-200",
    };
  }

  if (source === "scope_guard") return null; // handled by out_of_scope

  // LLM sources: groq / gemini
  return {
    label: "AI-Powered Analysis",
    icon: (
      <svg
        viewBox="0 0 24 24"
        className="h-3.5 w-3.5"
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z"
        />
      </svg>
    ),
    color: "text-blue-700",
    bgColor: "bg-blue-50",
    borderColor: "border-blue-200",
  };
}

// ---------------------------------------------------------------------------
// Main ChatInterface
// ---------------------------------------------------------------------------

export default function ChatInterface({
  sessionId,
  productName,
}: ChatInterfaceProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [topKeywords, setTopKeywords] = useState<KeywordData[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetchChatHistory(sessionId)
      .then((data) => {
        if (data.messages.length > 0) {
          setMessages(
            data.messages.map((m) => ({
              role: m.role,
              content: m.content,
              scopeStatus: m.scope_status,
            }))
          );
        }
      })
      .catch(() => {});

    fetchSummary(sessionId)
      .then((summary) => setTopKeywords(summary.top_keywords || []))
      .catch(() => {});
  }, [sessionId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, loading]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  async function handleSend(query?: string) {
    const q = (query || input).trim();
    if (!q || loading) return;

    setInput("");
    setError("");
    setMessages((prev) => [
      ...prev,
      { role: "user", content: q, scopeStatus: "" },
    ]);
    setLoading(true);

    const placeholderIdx = messages.length + 1;
    let streamingText = "";

    try {
      await sendChatStream(sessionId, q, (event: SSEEvent) => {
        if (event.type === "meta") {
          setMessages((prev) => {
            const filtered = prev.filter((_, i) => i !== placeholderIdx);
            return [
              ...filtered,
              {
                role: "assistant" as const,
                content: event.reply,
                scopeStatus: event.scope_status,
                source: event.source,
                model: event.model,
                citedReviews: event.cited_reviews,
                cached: event.cached,
                confidence: event.confidence,
              },
            ];
          });
          setLoading(false);
        } else if (event.type === "token") {
          streamingText += event.content;
          const currentText = streamingText;
          setMessages((prev) => {
            const lastMsg = prev[prev.length - 1];
            if (
              lastMsg &&
              lastMsg.role === "assistant" &&
              lastMsg.scopeStatus === "streaming"
            ) {
              return [
                ...prev.slice(0, -1),
                { ...lastMsg, content: currentText },
              ];
            }
            return [
              ...prev,
              {
                role: "assistant" as const,
                content: currentText,
                scopeStatus: "streaming",
                source: "llm",
              },
            ];
          });
          setLoading(false);
        } else if (event.type === "done") {
          const finalContent = event.replaced
            ? event.reply || ""
            : streamingText;
          setMessages((prev) => {
            const lastMsg = prev[prev.length - 1];
            if (lastMsg && lastMsg.role === "assistant") {
              return [
                ...prev.slice(0, -1),
                {
                  role: "assistant" as const,
                  content: finalContent,
                  scopeStatus: event.scope_status,
                  source: event.source,
                  model: event.model,
                  citedReviews: event.cited_reviews,
                  cached: event.cached,
                  confidence: event.confidence,
                },
              ];
            }
            return prev;
          });
        } else if (event.type === "error") {
          setError(event.detail);
          setMessages((prev) => [
            ...prev,
            {
              role: "assistant" as const,
              content: event.detail,
              scopeStatus: "error",
            },
          ]);
          setLoading(false);
        }
      });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Something went wrong";
      setError(msg);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant" as const,
          content: msg,
          scopeStatus: "error",
        },
      ]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  }

  return (
    <div className="flex flex-col h-[calc(100vh-97px)] sm:h-[calc(100vh-57px)]">
      {/* Messages area */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto chat-scroll px-4 sm:px-6 py-6"
      >
        {messages.length === 0 && !loading && (
          <EmptyState productName={productName} keywords={topKeywords} onSelect={(q) => handleSend(q)} />
        )}

        <div className="max-w-3xl mx-auto space-y-5">
          {messages.map((msg, i) => (
            <ChatBubble key={i} message={msg} />
          ))}
          {loading && (
            <div className="flex gap-3 items-start">
              <Avatar role="assistant" />
              <div className="bg-white border border-gray-200 rounded-2xl rounded-tl-sm shadow-sm">
                <TypingDots />
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Input bar */}
      <div className="border-t border-gray-200 bg-white/80 backdrop-blur-sm p-4">
        <div className="max-w-3xl mx-auto">
          {error && (
            <p className="text-xs text-red-500 mb-2 px-1">{error}</p>
          )}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();
            }}
            className="flex gap-2"
          >
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about the reviews..."
              disabled={loading}
              className="flex-1 rounded-xl border border-gray-300 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50 bg-white"
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 px-5 py-3 text-sm font-medium text-white hover:from-blue-700 hover:to-indigo-700 transition-all disabled:opacity-40 shadow-sm"
            >
              <svg
                viewBox="0 0 24 24"
                className="h-5 w-5"
                fill="none"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5"
                />
              </svg>
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ChatBubble — single message
// ---------------------------------------------------------------------------

function ChatBubble({ message }: { message: Message }) {
  const isUser = message.role === "user";
  const isOutOfScope = message.scopeStatus === "out_of_scope";
  const isError = message.scopeStatus === "error";
  const isStreaming = message.scopeStatus === "streaming";
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const cited = message.citedReviews || [];
  const sourceInfo = getSourceInfo(message);

  function handleCiteClick(id: number) {
    setExpandedId((prev) => (prev === id ? null : id));
  }

  const expandedReview = cited.find((r) => r.id === expandedId);

  // User message
  if (isUser) {
    return (
      <div className="flex gap-3 justify-end">
        <div className="max-w-[80%]">
          <div className="rounded-2xl rounded-tr-sm px-4 py-3 text-sm leading-relaxed bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-sm">
            {message.content}
          </div>
        </div>
        <Avatar role="user" />
      </div>
    );
  }

  // Out of scope message
  if (isOutOfScope) {
    return (
      <div className="flex gap-3 items-start">
        <Avatar role="assistant" />
        <div className="max-w-[80%] space-y-1.5">
          <div className="rounded-2xl rounded-tl-sm overflow-hidden border border-amber-200 shadow-sm">
            {/* Header */}
            <div className="bg-amber-50 px-4 py-2 flex items-center gap-2 border-b border-amber-200">
              <svg
                viewBox="0 0 20 20"
                className="h-4 w-4 text-amber-500"
                fill="currentColor"
              >
                <path
                  fillRule="evenodd"
                  d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.253a.25.25 0 01.244.304l-.459 2.066A1.75 1.75 0 0010.747 15H11a.75.75 0 000-1.5h-.253a.25.25 0 01-.244-.304l.459-2.066A1.75 1.75 0 009.253 9H9z"
                  clipRule="evenodd"
                />
              </svg>
              <span className="text-xs font-semibold text-amber-700">
                Outside Review Scope
              </span>
            </div>
            {/* Body */}
            <div className="bg-white px-4 py-3 text-sm text-gray-700 leading-relaxed">
              {renderMarkdown(message.content)}
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Error message
  if (isError) {
    return (
      <div className="flex gap-3 items-start">
        <Avatar role="assistant" />
        <div className="max-w-[80%]">
          <div className="rounded-2xl rounded-tl-sm overflow-hidden border border-red-200 shadow-sm">
            <div className="bg-red-50 px-4 py-2 flex items-center gap-2 border-b border-red-200">
              <svg
                viewBox="0 0 20 20"
                className="h-4 w-4 text-red-500"
                fill="currentColor"
              >
                <path
                  fillRule="evenodd"
                  d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z"
                  clipRule="evenodd"
                />
              </svg>
              <span className="text-xs font-semibold text-red-600">
                Something went wrong
              </span>
            </div>
            <div className="bg-white px-4 py-3 text-sm text-gray-700 leading-relaxed">
              {message.content}
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Normal assistant message (deterministic / LLM / cache / streaming)
  return (
    <div className="flex gap-3 items-start">
      <Avatar role="assistant" />
      <div className="max-w-[80%] space-y-1.5">
        {/* Source header badge */}
        {sourceInfo && !isStreaming && (
          <div
            className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold ${sourceInfo.color} ${sourceInfo.bgColor} ${sourceInfo.borderColor}`}
          >
            {sourceInfo.icon}
            {sourceInfo.label}
            {message.cached && (
              <span className="ml-1 opacity-70">&middot; Instant</span>
            )}
          </div>
        )}

        {/* Streaming indicator */}
        {isStreaming && (
          <div className="inline-flex items-center gap-1.5 rounded-full border border-blue-200 bg-blue-50 px-2.5 py-1 text-[11px] font-semibold text-blue-600">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500" />
            </span>
            Analyzing reviews...
          </div>
        )}

        {/* Message body */}
        <div className="rounded-2xl rounded-tl-sm bg-white border border-gray-200 shadow-sm px-4 py-3 text-sm text-gray-800 leading-relaxed">
          {renderContent(message.content, cited, handleCiteClick)}
        </div>

        {/* Expanded citation card */}
        {expandedReview && (
          <div className="border border-blue-200 bg-gradient-to-br from-blue-50 to-indigo-50 rounded-xl p-3.5 space-y-2 shadow-sm">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-blue-700">
                  Review #{expandedReview.id}
                </span>
                <span className="text-xs text-amber-500">
                  {"★".repeat(Math.round(expandedReview.rating))}
                  <span className="text-gray-300">
                    {"★".repeat(5 - Math.round(expandedReview.rating))}
                  </span>
                </span>
                {expandedReview.verified && (
                  <span className="inline-flex items-center gap-0.5 rounded-full bg-green-100 px-1.5 py-0.5 text-[10px] font-medium text-green-700">
                    <svg
                      viewBox="0 0 16 16"
                      className="h-2.5 w-2.5"
                      fill="currentColor"
                    >
                      <path
                        fillRule="evenodd"
                        d="M12.416 3.376a.75.75 0 01.208 1.04l-5 7.5a.75.75 0 01-1.154.114l-3-3a.75.75 0 011.06-1.06l2.353 2.353 4.493-6.74a.75.75 0 011.04-.207z"
                        clipRule="evenodd"
                      />
                    </svg>
                    Verified
                  </span>
                )}
              </div>
              <button
                onClick={() => setExpandedId(null)}
                className="text-gray-400 hover:text-gray-600 transition-colors"
              >
                <svg
                  viewBox="0 0 20 20"
                  className="h-4 w-4"
                  fill="currentColor"
                >
                  <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
                </svg>
              </button>
            </div>
            {expandedReview.title && (
              <p className="text-xs font-semibold text-gray-800">
                "{expandedReview.title}"
              </p>
            )}
            <p className="text-xs text-gray-600 leading-relaxed">
              {expandedReview.body}
            </p>
            <div className="flex items-center gap-3 text-[10px] text-gray-400 pt-1 border-t border-blue-100">
              {expandedReview.author && <span>by {expandedReview.author}</span>}
              {expandedReview.date && <span>{expandedReview.date}</span>}
              {expandedReview.helpful_votes > 0 && (
                <span>{expandedReview.helpful_votes} helpful votes</span>
              )}
            </div>
          </div>
        )}

        {/* Citation pill strip */}
        {cited.length > 0 && (
          <div className="flex items-center gap-1.5 flex-wrap px-1">
            <span className="text-[10px] text-gray-400 font-medium">
              Evidence:
            </span>
            {cited.map((r) => (
              <button
                key={r.id}
                onClick={() => handleCiteClick(r.id)}
                className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium transition-all ${
                  expandedId === r.id
                    ? "bg-blue-600 text-white shadow-sm"
                    : "bg-gray-100 text-gray-600 hover:bg-blue-100 hover:text-blue-700"
                }`}
              >
                #{r.id}{" "}
                <span className="text-amber-500 text-[9px]">
                  {"★".repeat(Math.round(r.rating))}
                </span>
              </button>
            ))}
          </div>
        )}

        {/* Footer metadata */}
        {message.source && !isStreaming && (
          <div className="flex items-center gap-2 px-1">
            {message.confidence != null && message.confidence > 0 && (
              <ConfidenceBadge value={message.confidence} />
            )}
            {message.model && message.source !== "deterministic" && message.source !== "scope_guard" && (
              <span className="text-[10px] text-gray-400">
                {message.source === "cache"
                  ? "Previously computed"
                  : `via ${message.model}`}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ConfidenceBadge({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color =
    pct >= 80
      ? "text-emerald-700 bg-emerald-50 border-emerald-200"
      : pct >= 50
        ? "text-amber-700 bg-amber-50 border-amber-200"
        : "text-red-600 bg-red-50 border-red-200";

  const label = pct >= 80 ? "High" : pct >= 50 ? "Medium" : "Low";

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold tabular-nums ${color}`}
    >
      <svg viewBox="0 0 16 16" className="h-3 w-3" fill="currentColor">
        <path
          fillRule="evenodd"
          d="M8 1.5a6.5 6.5 0 100 13 6.5 6.5 0 000-13zM0 8a8 8 0 1116 0A8 8 0 010 8z"
          clipRule="evenodd"
        />
        <path d="M8 4a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 018 4zm0 8a1 1 0 100-2 1 1 0 000 2z" />
      </svg>
      {label} confidence ({pct}%)
    </span>
  );
}

function Avatar({ role }: { role: "user" | "assistant" }) {
  if (role === "user") {
    return (
      <div className="shrink-0 h-8 w-8 rounded-full bg-gray-200 flex items-center justify-center">
        <svg
          viewBox="0 0 24 24"
          className="h-4 w-4 text-gray-500"
          fill="currentColor"
        >
          <path
            fillRule="evenodd"
            d="M7.5 6a4.5 4.5 0 119 0 4.5 4.5 0 01-9 0zM3.751 20.105a8.25 8.25 0 0116.498 0 .75.75 0 01-.437.695A18.683 18.683 0 0112 22.5c-2.786 0-5.433-.608-7.812-1.7a.75.75 0 01-.437-.695z"
            clipRule="evenodd"
          />
        </svg>
      </div>
    );
  }
  return (
    <div className="shrink-0 h-8 w-8 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center shadow-sm">
      <svg
        viewBox="0 0 24 24"
        className="h-4 w-4 text-white"
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 00-2.455 2.456z"
        />
      </svg>
    </div>
  );
}

function EmptyState({
  productName,
  keywords,
  onSelect,
}: {
  productName: string;
  keywords: KeywordData[];
  onSelect: (q: string) => void;
}) {
  const questions = buildSuggestedQuestions(productName, keywords);

  return (
    <div className="max-w-2xl mx-auto text-center py-8 sm:py-12 px-4 space-y-6">
      <div className="inline-flex items-center justify-center h-16 w-16 rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-600 shadow-lg">
        <svg
          viewBox="0 0 24 24"
          className="h-8 w-8 text-white"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.5}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 00-2.455 2.456z"
          />
        </svg>
      </div>
      <div>
        <h2 className="text-xl font-bold text-gray-900 mb-1">
          Talk to your reviews
        </h2>
        <p className="text-sm text-gray-500">
          Ask questions about{" "}
          <span className="font-medium text-gray-700">{productName}</span>{" "}
          reviews. The AI will only answer from ingested data.
        </p>
      </div>
      <div className="flex flex-wrap gap-2 justify-center">
        {questions.map((q) => (
          <button
            key={q}
            onClick={() => onSelect(q)}
            className="rounded-full border border-gray-200 bg-white px-4 py-2 text-sm text-gray-600 hover:border-blue-300 hover:text-blue-700 hover:bg-blue-50 transition-all shadow-sm"
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}
