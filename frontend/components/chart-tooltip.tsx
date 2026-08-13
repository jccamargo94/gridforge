import type { TooltipPayload } from "recharts";
import { formatNumber, formatHourLabel } from "@/lib/chart-format";

interface ChartTooltipProps {
  active?: boolean;
  payload?: TooltipPayload;
  label?: string | number;
  unit?: string;
  hourLabel?: string;
}

export function ChartTooltip({ active, payload, label, unit, hourLabel }: ChartTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;

  const hour = typeof label === "number" ? formatHourLabel(label) : String(label ?? "");

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/95 px-3 py-2 text-[13px] text-zinc-50 shadow-xl backdrop-blur">
      {hour && (
        <p className="mb-1.5 font-medium text-zinc-200">
          {hourLabel ? `${hourLabel}: ` : ""}
          <span className="tabular-nums">{hour}</span>
        </p>
      )}
      <ul className="space-y-1">
        {payload.map((entry) => {
          const raw = Array.isArray(entry.value) ? entry.value[0] : entry.value;
          const num = typeof raw === "number" ? raw : Number(raw ?? NaN);
          return (
            <li key={String(entry.dataKey ?? entry.name)} className="flex items-center gap-2 tabular-nums">
              <span
                className="inline-block size-2 shrink-0 rounded-full"
                style={{ backgroundColor: entry.color ?? entry.stroke ?? "#a1a1aa" }}
              />
              <span className="text-zinc-300">{entry.name}</span>
              <span className="ml-auto pl-4 font-medium text-zinc-50">
                {formatNumber(num)}
                {unit && (
                  <span className="ml-1 text-xs font-normal text-zinc-400">{unit}</span>
                )}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
