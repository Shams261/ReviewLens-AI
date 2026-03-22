import { useRef, useState } from "react";
import Spinner from "./Spinner";

interface HeaderProps {
  hasSession: boolean;
  productName: string;
  activeView: "dashboard" | "chat";
  onViewChange: (v: "dashboard" | "chat") => void;
  onGoHome: () => void;
  onLoadDemo: () => void;
  onUploadCSV: (file: File) => void;
  onIngestUrl: (url: string) => void;
  loading: boolean;
}

export default function Header({
  hasSession,
  productName,
  activeView,
  onViewChange,
  onGoHome,
  onLoadDemo,
  onUploadCSV,
  onIngestUrl,
  loading,
}: HeaderProps) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [urlInput, setUrlInput] = useState("");
  const [showUrlInput, setShowUrlInput] = useState(false);

  function handleFile(file: File | undefined) {
    if (file && file.name.toLowerCase().endsWith(".csv")) {
      onUploadCSV(file);
    }
  }

  return (
    <header className="bg-white/80 backdrop-blur-xl border-b border-gray-200/60 sticky top-0 z-30">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3 flex items-center justify-between gap-3">
        {/* Logo — clickable to go home */}
        <button
          onClick={onGoHome}
          className="flex items-center gap-2 shrink-0 group"
          title="Back to home"
        >
          <div className="flex items-center justify-center h-9 w-9 rounded-xl bg-gradient-to-br from-blue-600 to-indigo-600 shadow-md shadow-blue-200/50 group-hover:shadow-lg group-hover:shadow-blue-300/50 transition-all group-hover:scale-105">
            <svg viewBox="0 0 24 24" className="h-5 w-5 text-white" fill="none" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
            </svg>
          </div>
          <div className="hidden sm:flex items-center gap-1.5">
            <span className="text-lg font-bold text-gray-900 tracking-tight group-hover:text-blue-600 transition-colors">
              Review<span className="text-blue-600">Lens</span>
            </span>
            <span className="text-[9px] font-bold bg-gradient-to-r from-blue-600 to-indigo-600 text-white px-1.5 py-0.5 rounded-md uppercase tracking-wider">
              AI
            </span>
          </div>
        </button>

        {/* Nav tabs (only visible when session exists) */}
        {hasSession && (
          <div className="hidden sm:flex items-center bg-gray-100/80 rounded-xl p-1 gap-0.5">
            <button
              onClick={() => onViewChange("dashboard")}
              className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                activeView === "dashboard"
                  ? "bg-white text-gray-900 shadow-sm"
                  : "text-gray-500 hover:text-gray-700 hover:bg-white/50"
              }`}
            >
              <svg viewBox="0 0 20 20" className="h-4 w-4" fill="currentColor">
                <path d="M2 4.25A2.25 2.25 0 014.25 2h2.5A2.25 2.25 0 019 4.25v2.5A2.25 2.25 0 016.75 9h-2.5A2.25 2.25 0 012 6.75v-2.5zM2 13.25A2.25 2.25 0 014.25 11h2.5A2.25 2.25 0 019 13.25v2.5A2.25 2.25 0 016.75 18h-2.5A2.25 2.25 0 012 15.75v-2.5zM11 4.25A2.25 2.25 0 0113.25 2h2.5A2.25 2.25 0 0118 4.25v2.5A2.25 2.25 0 0115.75 9h-2.5A2.25 2.25 0 0111 6.75v-2.5zM11 13.25A2.25 2.25 0 0113.25 11h2.5A2.25 2.25 0 0118 13.25v2.5A2.25 2.25 0 0115.75 18h-2.5A2.25 2.25 0 0111 15.75v-2.5z" />
              </svg>
              Dashboard
            </button>
            <button
              onClick={() => onViewChange("chat")}
              className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                activeView === "chat"
                  ? "bg-white text-gray-900 shadow-sm"
                  : "text-gray-500 hover:text-gray-700 hover:bg-white/50"
              }`}
            >
              <svg viewBox="0 0 20 20" className="h-4 w-4" fill="currentColor">
                <path fillRule="evenodd" d="M10 2c-2.236 0-4.43.18-6.57.524C1.993 2.755 1 4.014 1 5.426v5.148c0 1.413.993 2.67 2.43 2.902 1.168.188 2.352.327 3.55.414.28.02.521.18.642.413l1.713 3.293a.75.75 0 001.33 0l1.713-3.293a.783.783 0 01.642-.413 41.102 41.102 0 003.55-.414c1.437-.231 2.43-1.49 2.43-2.902V5.426c0-1.413-.993-2.67-2.43-2.902A41.289 41.289 0 0010 2zM6.75 6a.75.75 0 000 1.5h6.5a.75.75 0 000-1.5h-6.5zm0 2.5a.75.75 0 000 1.5h3.5a.75.75 0 000-1.5h-3.5z" clipRule="evenodd" />
              </svg>
              Chat
            </button>
          </div>
        )}

        {/* Product name badge */}
        {hasSession && productName && (
          <div className="hidden lg:flex items-center gap-2 text-sm text-gray-500 bg-emerald-50 border border-emerald-200/60 rounded-lg px-3 py-1.5">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
            </span>
            <span className="text-emerald-700 font-medium truncate max-w-[200px]">{productName}</span>
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center gap-2 shrink-0">
          {loading && <Spinner size="sm" />}

          {/* URL input toggle + inline form */}
          {showUrlInput ? (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const url = urlInput.trim();
                if (url) {
                  onIngestUrl(url);
                  setUrlInput("");
                  setShowUrlInput(false);
                }
              }}
              className="flex items-center gap-1.5"
            >
              <input
                type="url"
                value={urlInput}
                onChange={(e) => setUrlInput(e.target.value)}
                placeholder="Amazon product URL..."
                disabled={loading}
                autoFocus
                className="w-40 sm:w-56 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50"
              />
              <button
                type="submit"
                disabled={loading || !urlInput.trim()}
                className="rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-all disabled:opacity-40"
              >
                Go
              </button>
              <button
                type="button"
                onClick={() => { setShowUrlInput(false); setUrlInput(""); }}
                className="rounded-lg border border-gray-300 px-2 py-2 text-sm text-gray-500 hover:bg-gray-50"
              >
                <svg viewBox="0 0 20 20" className="h-4 w-4" fill="currentColor">
                  <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
                </svg>
              </button>
            </form>
          ) : (
            <button
              onClick={() => setShowUrlInput(true)}
              disabled={loading}
              className="hidden sm:inline-flex rounded-lg border border-gray-200 px-3 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 hover:border-gray-300 transition-all disabled:opacity-50"
            >
              Paste URL
            </button>
          )}

          <input
            ref={fileRef}
            type="file"
            accept=".csv"
            className="hidden"
            onChange={(e) => handleFile(e.target.files?.[0])}
          />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={loading}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              handleFile(e.dataTransfer.files[0]);
            }}
            className={`hidden sm:inline-flex rounded-lg border px-3 py-2 text-sm font-medium transition-all disabled:opacity-50
              ${dragOver
                ? "border-blue-400 bg-blue-50 text-blue-700"
                : "border-gray-200 text-gray-600 hover:bg-gray-50 hover:border-gray-300"
              }`}
          >
            CSV
          </button>

          <button
            onClick={onLoadDemo}
            disabled={loading}
            className="rounded-lg bg-gradient-to-r from-blue-600 to-indigo-600 px-3 sm:px-4 py-2 text-sm font-medium text-white hover:from-blue-700 hover:to-indigo-700 transition-all disabled:opacity-50 shadow-sm hover:shadow-md"
          >
            Demo
          </button>
        </div>
      </div>

      {/* Mobile nav */}
      {hasSession && (
        <div className="sm:hidden flex border-t border-gray-100">
          <button
            onClick={() => onViewChange("dashboard")}
            className={`flex-1 flex items-center justify-center gap-1.5 py-2.5 text-sm font-medium ${
              activeView === "dashboard"
                ? "text-blue-600 border-b-2 border-blue-600 bg-blue-50/50"
                : "text-gray-500"
            }`}
          >
            <svg viewBox="0 0 20 20" className="h-4 w-4" fill="currentColor">
              <path d="M2 4.25A2.25 2.25 0 014.25 2h2.5A2.25 2.25 0 019 4.25v2.5A2.25 2.25 0 016.75 9h-2.5A2.25 2.25 0 012 6.75v-2.5zM2 13.25A2.25 2.25 0 014.25 11h2.5A2.25 2.25 0 019 13.25v2.5A2.25 2.25 0 016.75 18h-2.5A2.25 2.25 0 012 15.75v-2.5zM11 4.25A2.25 2.25 0 0113.25 2h2.5A2.25 2.25 0 0118 4.25v2.5A2.25 2.25 0 0115.75 9h-2.5A2.25 2.25 0 0111 6.75v-2.5zM11 13.25A2.25 2.25 0 0113.25 11h2.5A2.25 2.25 0 0118 13.25v2.5A2.25 2.25 0 0115.75 18h-2.5A2.25 2.25 0 0111 15.75v-2.5z" />
            </svg>
            Dashboard
          </button>
          <button
            onClick={() => onViewChange("chat")}
            className={`flex-1 flex items-center justify-center gap-1.5 py-2.5 text-sm font-medium ${
              activeView === "chat"
                ? "text-blue-600 border-b-2 border-blue-600 bg-blue-50/50"
                : "text-gray-500"
            }`}
          >
            <svg viewBox="0 0 20 20" className="h-4 w-4" fill="currentColor">
              <path fillRule="evenodd" d="M10 2c-2.236 0-4.43.18-6.57.524C1.993 2.755 1 4.014 1 5.426v5.148c0 1.413.993 2.67 2.43 2.902 1.168.188 2.352.327 3.55.414.28.02.521.18.642.413l1.713 3.293a.75.75 0 001.33 0l1.713-3.293a.783.783 0 01.642-.413 41.102 41.102 0 003.55-.414c1.437-.231 2.43-1.49 2.43-2.902V5.426c0-1.413-.993-2.67-2.43-2.902A41.289 41.289 0 0010 2zM6.75 6a.75.75 0 000 1.5h6.5a.75.75 0 000-1.5h-6.5zm0 2.5a.75.75 0 000 1.5h3.5a.75.75 0 000-1.5h-3.5z" clipRule="evenodd" />
            </svg>
            Chat
          </button>
        </div>
      )}
    </header>
  );
}
