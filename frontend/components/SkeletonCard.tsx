export function SkeletonCard({ lines = 5 }: { lines?: number }) {
  return (
    <div className="rounded-card border border-border bg-bg-secondary p-4 animate-pulse">
      <div className="flex flex-col gap-2">
        {Array.from({ length: lines }).map((_, i) => (
          <div
            // eslint-disable-next-line react/no-array-index-key
            key={i}
            className="h-3 rounded bg-border/50"
            style={{ width: `${80 - i * 7}%` }}
          />
        ))}
      </div>
    </div>
  );
}

