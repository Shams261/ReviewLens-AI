import { useState } from "react";
import Header from "./components/Header";
import WelcomeScreen from "./components/WelcomeScreen";
import Dashboard from "./components/Dashboard";
import ChatInterface from "./components/ChatInterface";
import Footer from "./components/Footer";
import {
  loadDemo,
  uploadCSV,
  ingestUrlStream,
  type IngestResponse,
  type IngestSSEEvent,
} from "./lib/api";

type View = "dashboard" | "chat";

export default function App() {
  const [session, setSession] = useState<IngestResponse | null>(null);
  const [activeView, setActiveView] = useState<View>("dashboard");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [ingestProgress, setIngestProgress] = useState("");

  function handleGoHome() {
    setSession(null);
    setActiveView("dashboard");
    setError("");
  }

  async function handleLoadDemo() {
    setLoading(true);
    setError("");
    try {
      const res = await loadDemo();
      setSession(res);
      setActiveView("dashboard");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load demo data");
    } finally {
      setLoading(false);
    }
  }

  async function handleUploadCSV(file: File) {
    setLoading(true);
    setError("");
    try {
      const res = await uploadCSV(file, file.name.replace(/\.csv$/i, ""));
      setSession(res);
      setActiveView("dashboard");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to upload CSV");
    } finally {
      setLoading(false);
    }
  }

  async function handleIngestUrl(url: string) {
    setLoading(true);
    setError("");
    setIngestProgress("Connecting to Amazon...");
    try {
      let done = false;
      await ingestUrlStream(url, (event: IngestSSEEvent) => {
        if (event.type === "progress") {
          if (event.page === 0) {
            setIngestProgress("Validating URL and starting scrape...");
          } else if (event.page === -1) {
            setIngestProgress(
              `Saving ${event.reviews_found} reviews to database...`,
            );
          } else {
            setIngestProgress(
              `Fetching page ${event.page}/${event.max_pages}... ${event.reviews_found} reviews found`,
            );
          }
        } else if (event.type === "done") {
          done = true;
          setSession({
            session_id: event.session_id,
            product_name: event.product_name,
            platform: event.platform,
            review_count: event.review_count,
            source: event.source,
          });
          setActiveView("dashboard");
        } else if (event.type === "error") {
          setError(event.detail);
        }
      });
      if (!done && !error) {
        setError("Stream ended without completing. Try again.");
      }
    } catch (e: unknown) {
      setError(
        e instanceof Error ? e.message : "Failed to fetch reviews from URL",
      );
    } finally {
      setLoading(false);
      setIngestProgress("");
    }
  }

  const showFooter = !session || activeView === "dashboard";

  return (
    <div className="min-h-screen flex flex-col bg-linear-to-br from-slate-50 via-white to-blue-50/30">
      <Header
        hasSession={!!session}
        productName={session?.product_name || ""}
        activeView={activeView}
        onViewChange={setActiveView}
        onGoHome={handleGoHome}
        onLoadDemo={handleLoadDemo}
        onUploadCSV={handleUploadCSV}
        onIngestUrl={handleIngestUrl}
        loading={loading}
      />

      {/* Error banner */}
      {error && (
        <div className="bg-red-50 border-b border-red-200 px-4 py-3">
          <div className="max-w-7xl mx-auto flex items-center justify-between">
            <p className="text-sm text-red-700">{error}</p>
            <button
              onClick={() => setError("")}
              className="text-red-400 hover:text-red-600"
            >
              <svg viewBox="0 0 20 20" className="h-4 w-4" fill="currentColor">
                <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
              </svg>
            </button>
          </div>
        </div>
      )}

      {/* Main content */}
      <div className="flex-1">
        {!session ? (
          <WelcomeScreen
            onLoadDemo={handleLoadDemo}
            onUploadCSV={handleUploadCSV}
            onIngestUrl={handleIngestUrl}
            loading={loading}
            progressMessage={ingestProgress}
          />
        ) : activeView === "dashboard" ? (
          <main className="max-w-7xl mx-auto">
            <Dashboard sessionId={session.session_id} />
          </main>
        ) : (
          <ChatInterface
            sessionId={session.session_id}
            productName={session.product_name}
          />
        )}
      </div>

      {showFooter && <Footer />}
    </div>
  );
}
