interface StarBarProps {
  star: number;
  count: number;
  maxCount: number;
}

const STAR_COLORS: Record<number, string> = {
  5: "bg-emerald-500",
  4: "bg-green-400",
  3: "bg-yellow-400",
  2: "bg-orange-400",
  1: "bg-red-400",
};

export default function StarBar({ star, count, maxCount }: StarBarProps) {
  const pct = maxCount > 0 ? (count / maxCount) * 100 : 0;

  return (
    <div className="flex items-center gap-3 group">
      <span className="text-sm font-medium text-gray-600 w-12 text-right shrink-0">
        {star} star
      </span>
      <div className="flex-1 h-4 bg-gray-100 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full ${STAR_COLORS[star]} transition-all duration-700 ease-out`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-sm font-semibold text-gray-700 w-8 text-right tabular-nums">
        {count}
      </span>
    </div>
  );
}
