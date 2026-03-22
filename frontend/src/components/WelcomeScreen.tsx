import { useState } from "react";
import Spinner from "./Spinner";

interface WelcomeScreenProps {
  onLoadDemo: () => void;
  onUploadCSV: (file: File) => void;
  onIngestUrl: (url: string) => void;
  loading: boolean;
  progressMessage?: string;
}

export default function WelcomeScreen({
  onLoadDemo,
  onUploadCSV,
  onIngestUrl,
  loading,
  progressMessage,
}: WelcomeScreenProps) {
  const [url, setUrl] = useState("");

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file?.name.toLowerCase().endsWith(".csv")) onUploadCSV(file);
  }

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) onUploadCSV(file);
  }

  function handleUrlSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = url.trim();
    if (trimmed) onIngestUrl(trimmed);
  }

  return (
    <div className="flex items-center justify-center min-h-[calc(100vh-57px)] px-4 py-8">
      <div className="max-w-xl w-full text-center space-y-8">
        {/* Hero */}
        <div className="space-y-6">
          <div className="inline-flex items-center justify-center h-20 w-20 rounded-2xl bg-gradient-to-br from-blue-600 to-indigo-600 shadow-xl shadow-blue-300/30">
            <svg viewBox="0 0 24 24" className="h-10 w-10 text-white" fill="none" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
            </svg>
          </div>

          <div className="space-y-3">
            <h1 className="text-4xl sm:text-5xl font-extrabold text-gray-900 tracking-tight">
              Review<span className="bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent">Lens</span> AI
            </h1>
            <p className="text-gray-500 text-lg max-w-md mx-auto leading-relaxed">
              Ingest product reviews and analyze them with guardrailed AI.
              No hallucinations, only evidence.
            </p>
          </div>
        </div>

        {loading ? (
          <div className="flex flex-col items-center gap-4 py-8">
            <div className="relative">
              <div className="absolute inset-0 rounded-full bg-blue-500/20 animate-ping" />
              <Spinner size="lg" />
            </div>
            <div className="space-y-1">
              <p className="text-sm font-medium text-gray-700">
                {progressMessage || "Fetching reviews..."}
              </p>
              <p className="text-xs text-gray-400">This may take a moment</p>
            </div>
          </div>
        ) : (
          <div className="space-y-5">
            {/* URL input */}
            <form onSubmit={handleUrlSubmit} className="relative">
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <div className="absolute inset-y-0 left-3.5 flex items-center pointer-events-none">
                    <svg viewBox="0 0 20 20" className="h-4.5 w-4.5 text-gray-400" fill="currentColor">
                      <path d="M12.232 4.232a2.5 2.5 0 013.536 3.536l-1.225 1.224a.75.75 0 001.061 1.06l1.224-1.224a4 4 0 00-5.656-5.656l-3 3a4 4 0 00.225 5.865.75.75 0 00.977-1.138 2.5 2.5 0 01-.142-3.667l3-3z" />
                      <path d="M11.603 7.963a.75.75 0 00-.977 1.138 2.5 2.5 0 01.142 3.667l-3 3a2.5 2.5 0 01-3.536-3.536l1.225-1.224a.75.75 0 00-1.061-1.06l-1.224 1.224a4 4 0 105.656 5.656l3-3a4 4 0 00-.225-5.865z" />
                    </svg>
                  </div>
                  <input
                    type="text"
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    placeholder="https://www.amazon.com/dp/B0D1XD1ZV3"
                    className="w-full rounded-xl border border-gray-200 pl-10 pr-4 py-3.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white shadow-sm hover:border-gray-300 transition-colors"
                  />
                </div>
                <button
                  type="submit"
                  disabled={!url.trim()}
                  className="rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 px-6 py-3.5 text-sm font-semibold text-white hover:from-blue-700 hover:to-indigo-700 transition-all disabled:opacity-40 shadow-md hover:shadow-lg shrink-0"
                >
                  Analyze
                </button>
              </div>
              <p className="text-xs text-gray-400 mt-2 text-left pl-1">
                Paste any Amazon product URL — we'll extract and analyze the reviews
              </p>
            </form>

            <div className="flex items-center gap-4 py-1">
              <hr className="flex-1 border-gray-200" />
              <span className="text-xs text-gray-400 uppercase font-medium tracking-wider">or</span>
              <hr className="flex-1 border-gray-200" />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {/* Demo button */}
              <button
                onClick={onLoadDemo}
                className="group rounded-xl border border-gray-200 bg-white px-5 py-5 text-left hover:border-blue-300 hover:bg-blue-50/30 transition-all shadow-sm hover:shadow-md"
              >
                <span className="flex items-center gap-3 mb-2">
                  <span className="flex items-center justify-center h-10 w-10 rounded-lg bg-blue-100 text-blue-600 group-hover:bg-blue-200 transition-colors">
                    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
                    </svg>
                  </span>
                  <span className="font-semibold text-gray-900">Load Demo</span>
                </span>
                <span className="text-xs text-gray-500 block pl-[52px]">
                  50 AirPods Pro reviews — instant setup
                </span>
              </button>

              {/* CSV upload */}
              <label
                onDragOver={(e) => e.preventDefault()}
                onDrop={handleDrop}
                className="group rounded-xl border border-gray-200 bg-white px-5 py-5 text-left hover:border-emerald-300 hover:bg-emerald-50/30 transition-all shadow-sm hover:shadow-md cursor-pointer"
              >
                <input
                  type="file"
                  accept=".csv"
                  className="hidden"
                  onChange={handleFileSelect}
                />
                <span className="flex items-center gap-3 mb-2">
                  <span className="flex items-center justify-center h-10 w-10 rounded-lg bg-emerald-100 text-emerald-600 group-hover:bg-emerald-200 transition-colors">
                    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
                    </svg>
                  </span>
                  <span className="font-semibold text-gray-900">Upload CSV</span>
                </span>
                <span className="text-xs text-gray-500 block pl-[52px]">
                  Drag & drop or click to browse
                </span>
              </label>
            </div>

            {/* Features */}
            <div className="grid grid-cols-3 gap-4 pt-4">
              {[
                { icon: "M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z", label: "Guardrailed AI" },
                { icon: "M3.75 3v11.25A2.25 2.25 0 006 16.5h2.25M3.75 3h-1.5m1.5 0h16.5m0 0h1.5m-1.5 0v11.25A2.25 2.25 0 0118 16.5h-2.25m-7.5 0h7.5m-7.5 0l-1 3m8.5-3l1 3m0 0l.5 1.5m-.5-1.5h-9.5m0 0l-.5 1.5", label: "Evidence-backed" },
                { icon: "M7.5 14.25v2.25m3-4.5v4.5m3-6.75v6.75m3-9v9M6 20.25h12A2.25 2.25 0 0020.25 18V6A2.25 2.25 0 0018 3.75H6A2.25 2.25 0 003.75 6v12A2.25 2.25 0 006 20.25z", label: "Real-time analytics" },
              ].map(({ icon, label }) => (
                <div key={label} className="text-center space-y-2">
                  <div className="inline-flex items-center justify-center h-10 w-10 rounded-lg bg-gray-100 text-gray-500">
                    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d={icon} />
                    </svg>
                  </div>
                  <p className="text-xs font-medium text-gray-600">{label}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
