import { cn } from "@/lib/utils";

export interface ChartLegendItem {
  key: string;
  name: string;
  color: string;
}

interface ChartLegendProps {
  items: ChartLegendItem[];
  hidden: ReadonlySet<string>;
  onToggle: (key: string) => void;
}

export function ChartLegend({ items, hidden, onToggle }: ChartLegendProps) {
  if (items.length === 0) return null;

  return (
    <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2">
      {items.map((item) => {
        const isHidden = hidden.has(item.key);
        return (
          <button
            key={item.key}
            type="button"
            onClick={() => onToggle(item.key)}
            aria-pressed={!isHidden}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs transition-colors",
              isHidden
                ? "border-zinc-800 text-zinc-500 hover:border-zinc-700 hover:text-zinc-300"
                : "border-zinc-700 text-zinc-200 hover:border-zinc-500"
            )}
          >
            <span
              className="inline-block size-2 rounded-full"
              style={{ backgroundColor: isHidden ? "#3f3f46" : item.color }}
            />
            <span className={isHidden ? "line-through" : undefined}>{item.name}</span>
          </button>
        );
      })}
    </div>
  );
}
