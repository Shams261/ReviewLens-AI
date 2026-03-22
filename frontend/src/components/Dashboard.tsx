import { useEffect, useState } from "react";
import { fetchSummary, fetchReviews, type SummaryResponse, type ReviewItem } from "../lib/api";
import Spinner from "./Spinner";
import StarBar from "./StarBar";

interface DashboardProps {
  sessionId: string;
}

export default function Dashboard({ sessionId }: DashboardProps) {
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Review panel state
  const [showReviews, setShowReviews] = useState(false);
  const [reviews, setReviews] = useState<ReviewItem[]>([]);
  const [reviewPage, setReviewPage] = useState(1);
  const [totalReviews, setTotalReviews] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [reviewsLoading, setReviewsLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError("");
    fetchSummary(sessionId)
      .then(setSummary)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [sessionId]);

  async function loadReviews(page: number) {
    setReviewsLoading(true);
    try {
      const data = await fetchReviews(sessionId, page, 15);
      if (page === 1) {
        setReviews(data.reviews);
      } else {
        setReviews((prev) => [...prev, ...data.reviews]);
      }
      setReviewPage(data.page);
      setTotalReviews(data.total);
      setTotalPages(data.pages);
    } catch (e) {
      // silently fail for reviews panel
    } finally {
      setReviewsLoading(false);
    }
  }

  function handleShowReviews() {
    if (!showReviews && reviews.length === 0) {
      loadReviews(1);
    }
    setShowReviews(!showReviews);
  }

  function handleLoadMore() {
    if (reviewPage < totalPages) {
      loadReviews(reviewPage + 1);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Spinner size="lg" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8 text-center text-red-500">
        Failed to load summary: {error}
      </div>
    );
  }

  if (!summary) return null;

  const maxStarCount = Math.max(
    ...Object.values(summary.star_distribution),
    1
  );

  const ratingColor =
    summary.average_rating >= 4
      ? "text-emerald-600"
      : summary.average_rating >= 3
        ? "text-yellow-600"
        : "text-red-500";

  const positiveCount = (summary.star_distribution["4"] || 0) + (summary.star_distribution["5"] || 0);
  const positivePct = summary.total_reviews > 0 ? ((positiveCount / summary.total_reviews) * 100).toFixed(0) : "0";

  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-6 animate-in">
      {/* Top stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        <StatCard
          label="Total Reviews"
          value={summary.total_reviews.toLocaleString()}
          sub={`${summary.date_range.earliest || "N/A"} — ${summary.date_range.latest || "N/A"}`}
          onClick={handleShowReviews}
          clickable
          icon={
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.087.16 2.185.283 3.293.369V21l4.076-4.076a1.526 1.526 0 011.037-.443 48.282 48.282 0 005.68-.494c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0012 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018z" />
            </svg>
          }
        />
        <StatCard
          label="Avg. Rating"
          value={summary.average_rating.toFixed(1)}
          valueClass={ratingColor}
          sub="out of 5.0"
          icon={
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor">
              <path d="M10.788 3.21c.448-1.077 1.976-1.077 2.424 0l2.082 5.006 5.404.434c1.164.093 1.636 1.545.749 2.305l-4.117 3.527 1.257 5.273c.271 1.136-.964 2.033-1.96 1.425L12 18.354 7.373 21.18c-.996.608-2.231-.29-1.96-1.425l1.257-5.273-4.117-3.527c-.887-.76-.415-2.212.749-2.305l5.404-.434 2.082-5.005z" />
            </svg>
          }
        />
        <StatCard
          label="Verified Purchases"
          value={`${summary.verified.percentage}%`}
          sub={`${summary.verified.count} of ${summary.total_reviews}`}
          icon={
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12c0 1.268-.63 2.39-1.593 3.068a3.745 3.745 0 01-1.043 3.296 3.745 3.745 0 01-3.296 1.043A3.745 3.745 0 0112 21c-1.268 0-2.39-.63-3.068-1.593a3.746 3.746 0 01-3.296-1.043 3.745 3.745 0 01-1.043-3.296A3.745 3.745 0 013 12c0-1.268.63-2.39 1.593-3.068a3.745 3.745 0 011.043-3.296 3.746 3.746 0 013.296-1.043A3.746 3.746 0 0112 3c1.268 0 2.39.63 3.068 1.593a3.746 3.746 0 013.296 1.043 3.746 3.746 0 011.043 3.296A3.745 3.745 0 0121 12z" />
            </svg>
          }
        />
        <StatCard
          label={`Positive (4-5)`}
          value={`${positivePct}%`}
          sub={`${positiveCount} reviews`}
          icon={
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 18L9 11.25l4.306 4.307a11.95 11.95 0 015.814-5.519l2.74-1.22m0 0l-5.94-2.28m5.94 2.28l-2.28 5.941" />
            </svg>
          }
        />
      </div>

      {/* Reviews Panel — toggles open when Total Reviews is clicked */}
      {showReviews && (
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
            <h3 className="text-sm font-semibold text-gray-900 uppercase tracking-wider">
              Reviews ({totalReviews})
            </h3>
            <button
              onClick={() => setShowReviews(false)}
              className="text-gray-400 hover:text-gray-600 transition-colors"
            >
              <svg viewBox="0 0 20 20" className="h-5 w-5" fill="currentColor">
                <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
              </svg>
            </button>
          </div>
          <div className="divide-y divide-gray-50 max-h-[600px] overflow-y-auto">
            {reviews.map((r) => (
              <ReviewCard key={r.id} review={r} />
            ))}
            {reviewsLoading && (
              <div className="flex justify-center py-6">
                <Spinner size="sm" />
              </div>
            )}
          </div>
          {reviewPage < totalPages && !reviewsLoading && (
            <div className="px-6 py-4 border-t border-gray-100 text-center">
              <button
                onClick={handleLoadMore}
                className="inline-flex items-center gap-2 rounded-lg bg-gray-100 px-5 py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-200 transition-colors"
              >
                Load more reviews
                <span className="text-xs text-gray-500">
                  ({reviews.length} of {totalReviews})
                </span>
              </button>
            </div>
          )}
        </div>
      )}

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Star distribution chart */}
        <div className="bg-white rounded-2xl border border-gray-200 p-6 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-900 uppercase tracking-wider mb-5">
            Rating Distribution
          </h3>
          <div className="space-y-3">
            {[5, 4, 3, 2, 1].map((star) => (
              <StarBar
                key={star}
                star={star}
                count={summary.star_distribution[String(star)] || 0}
                maxCount={maxStarCount}
              />
            ))}
          </div>
        </div>

        {/* Sentiment breakdown */}
        <div className="bg-white rounded-2xl border border-gray-200 p-6 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-900 uppercase tracking-wider mb-5">
            Sentiment Breakdown
          </h3>
          <div className="space-y-4">
            <SentimentBar label="Positive" count={summary.sentiment.positive} pct={summary.sentiment.positive_pct} color="bg-emerald-500" />
            <SentimentBar label="Neutral" count={summary.sentiment.neutral} pct={summary.sentiment.neutral_pct} color="bg-yellow-400" />
            <SentimentBar label="Negative" count={summary.sentiment.negative} pct={summary.sentiment.negative_pct} color="bg-red-500" />
          </div>
          <div className="mt-4 flex items-center gap-4 text-xs text-gray-400">
            <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-emerald-500" /> 4-5 stars</span>
            <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-yellow-400" /> 3 stars</span>
            <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-red-500" /> 1-2 stars</span>
          </div>
        </div>
      </div>

      {/* Top keywords */}
      {summary.top_keywords && summary.top_keywords.length > 0 && (
        <div className="bg-white rounded-2xl border border-gray-200 p-6 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-900 uppercase tracking-wider mb-5">
            Top Keywords
          </h3>
          <div className="flex flex-wrap gap-2">
            {summary.top_keywords.map((kw) => {
              const kwColor =
                kw.avg_rating >= 4 ? "bg-emerald-100 text-emerald-800 border-emerald-200"
                : kw.avg_rating >= 3 ? "bg-yellow-50 text-yellow-800 border-yellow-200"
                : "bg-red-50 text-red-800 border-red-200";
              return (
                <span
                  key={kw.word}
                  className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm font-medium ${kwColor}`}
                >
                  {kw.word}
                  <span className="text-[10px] opacity-60">
                    {kw.count}x | {kw.avg_rating.toFixed(1)}★
                  </span>
                </span>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// --- Review Card ---
function ReviewCard({ review }: { review: ReviewItem }) {
  const stars = "★".repeat(Math.round(review.rating)) + "☆".repeat(5 - Math.round(review.rating));
  const ratingColor =
    review.rating >= 4 ? "text-amber-500" : review.rating >= 3 ? "text-yellow-500" : "text-red-400";

  return (
    <div className="px-6 py-4 hover:bg-gray-50/50 transition-colors">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span className={`text-sm ${ratingColor}`}>{stars}</span>
            {review.verified && (
              <span className="text-[10px] font-medium text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded">
                Verified
              </span>
            )}
            {review.helpful_votes > 0 && (
              <span className="text-[10px] text-gray-400">
                {review.helpful_votes} found helpful
              </span>
            )}
          </div>
          {review.title && (
            <p className="text-sm font-medium text-gray-900 mb-1">{review.title}</p>
          )}
          <p className="text-sm text-gray-600 line-clamp-3">{review.body}</p>
          <div className="flex items-center gap-3 mt-2 text-xs text-gray-400">
            {review.author && <span>{review.author}</span>}
            {review.date && <span>{review.date}</span>}
          </div>
        </div>
      </div>
    </div>
  );
}

function SentimentBar({
  label,
  count,
  pct,
  color,
}: {
  label: string;
  count: number;
  pct: number;
  color: string;
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium text-gray-700">{label}</span>
        <span className="text-gray-500 tabular-nums">{count} ({pct}%)</span>
      </div>
      <div className="h-3 rounded-full bg-gray-100 overflow-hidden">
        <div
          className={`h-full rounded-full ${color} transition-all duration-500`}
          style={{ width: `${Math.max(pct, 1)}%` }}
        />
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  sub,
  icon,
  valueClass = "text-gray-900",
  onClick,
  clickable = false,
}: {
  label: string;
  value: string;
  sub: string;
  icon: React.ReactNode;
  valueClass?: string;
  onClick?: () => void;
  clickable?: boolean;
}) {
  const Wrapper = clickable ? "button" : "div";
  return (
    <Wrapper
      onClick={onClick}
      className={`bg-white rounded-2xl border border-gray-200 p-4 sm:p-5 shadow-sm hover:shadow-md transition-all text-left w-full ${
        clickable ? "cursor-pointer hover:border-blue-300 hover:bg-blue-50/20 group" : ""
      }`}
    >
      <div className="flex items-center justify-between mb-2 sm:mb-3">
        <span className="text-[10px] sm:text-xs font-semibold text-gray-500 uppercase tracking-wider">
          {label}
        </span>
        <span className={`text-gray-400 ${clickable ? "group-hover:text-blue-500 transition-colors" : ""}`}>{icon}</span>
      </div>
      <p className={`text-2xl sm:text-3xl font-bold tabular-nums ${valueClass}`}>{value}</p>
      <p className="text-[10px] sm:text-xs text-gray-400 mt-1 truncate">{sub}</p>
      {clickable && (
        <p className="text-[10px] text-blue-500 font-medium mt-2 opacity-0 group-hover:opacity-100 transition-opacity">
          Click to view reviews
        </p>
      )}
    </Wrapper>
  );
}
