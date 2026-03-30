export default function Footer() {
  return (
    <footer className="mt-auto shrink-0 border-t border-slate-200/80 bg-white">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3 sm:py-4">
        <div className="flex flex-wrap items-center justify-between gap-2 sm:gap-3">
          <div className="flex items-center gap-2 shrink-0">
            <div className="flex items-center justify-center h-8 w-8 rounded-xl bg-linear-to-br from-blue-600 to-indigo-600 shadow-md shadow-blue-200/50">
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
                  d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"
                />
              </svg>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-base font-bold text-gray-900 tracking-tight">
                Review<span className="text-blue-600">Lens</span>
              </span>
              <span className="text-[8px] font-bold bg-linear-to-r from-blue-600 to-indigo-600 text-white px-1.5 py-0.5 rounded-md uppercase tracking-wider">
                AI
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2 text-[11px] sm:text-xs font-semibold uppercase tracking-[0.12em] text-emerald-700 min-w-0">
            <span className="relative flex h-2 w-2 shrink-0">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
            </span>
            <span className="truncate">All systems operational</span>
            <span className="text-slate-300">|</span>
            <span className="normal-case font-medium tracking-normal text-slate-500 truncate">
              Built with{" "}
              <span className="text-rose-500">❤</span> by Shams
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-2 sm:justify-end">
            <a
              href="https://linkedin.com/in/shams-tabrez-169829167/"
              target="_blank"
              rel="noreferrer"
              className="inline-flex rounded-lg border border-gray-200 bg-white/80 px-3 py-1.5 text-sm font-medium text-gray-600 transition-all duration-200 ease-out hover:-translate-y-0.5 hover:border-blue-300 hover:text-slate-900 hover:shadow-[0_0_0_1px_rgba(59,130,246,0.10),0_8px_20px_-10px_rgba(37,99,235,0.45)] active:translate-y-0 active:shadow-[0_0_0_1px_rgba(59,130,246,0.14),0_4px_10px_-8px_rgba(37,99,235,0.5)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/40"
            >
              LinkedIn
            </a>
            <a
              href="https://github.com/Shams261/"
              target="_blank"
              rel="noreferrer"
              className="inline-flex rounded-lg border border-gray-200 bg-white/80 px-3 py-1.5 text-sm font-medium text-gray-600 transition-all duration-200 ease-out hover:-translate-y-0.5 hover:border-blue-300 hover:text-slate-900 hover:shadow-[0_0_0_1px_rgba(59,130,246,0.10),0_8px_20px_-10px_rgba(37,99,235,0.45)] active:translate-y-0 active:shadow-[0_0_0_1px_rgba(59,130,246,0.14),0_4px_10px_-8px_rgba(37,99,235,0.5)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/40"
            >
              GitHub
            </a>
            <a
              href="mailto:shamsshoaib261@gmail.com"
              className="inline-flex rounded-lg border border-gray-200 bg-white/80 px-3 py-1.5 text-sm font-medium text-gray-600 transition-all duration-200 ease-out hover:-translate-y-0.5 hover:border-blue-300 hover:text-slate-900 hover:shadow-[0_0_0_1px_rgba(59,130,246,0.10),0_8px_20px_-10px_rgba(37,99,235,0.45)] active:translate-y-0 active:shadow-[0_0_0_1px_rgba(59,130,246,0.14),0_4px_10px_-8px_rgba(37,99,235,0.5)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/40"
            >
              Email
            </a>
          </div>
        </div>
      </div>
    </footer>
  );
}
