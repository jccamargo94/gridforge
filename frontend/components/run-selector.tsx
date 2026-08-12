"use client";

import type { RunSummary } from "@/lib/types";
import { useT } from "@/lib/i18n-context";

export function RunSelector({
  runs,
  selectedIds,
  onToggle,
}: {
  runs: RunSummary[];
  selectedIds: string[];
  onToggle: (id: string) => void;
}) {
  const t = useT();
  const doneRuns = runs.filter((r) => r.status === "done");

  if (doneRuns.length === 0)
    return (
      <p className="text-sm text-muted-foreground">
        {t("compare.noCompleted")}
      </p>
    );

  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm text-muted-foreground">
        {t("compare.selectHint")}
      </p>
      <div className="max-h-80 overflow-y-auto flex flex-col gap-1">
        {doneRuns.map((run) => {
          const isSelected = selectedIds.includes(run.run_id);
          return (
            <label
              key={run.run_id}
              className={`flex items-center gap-3 rounded-lg border px-3 py-2.5 cursor-pointer transition-colors ${
                isSelected
                  ? "border-amber-500/50 bg-amber-500/5"
                  : "border-border hover:bg-accent/50"
              }`}
            >
              <input
                type="checkbox"
                checked={isSelected}
                onChange={() => onToggle(run.run_id)}
                className="size-4 rounded border-border accent-amber-500"
              />
              <div className="flex flex-1 items-center justify-between min-w-0">
                <span className="text-sm font-medium truncate">
                  {run.dispatch_date}{" "}
                  <span className="text-muted-foreground">({run.level})</span>
                </span>
                {run.scenario_id && (
                  <span className="text-xs text-muted-foreground shrink-0 ml-2">
                    {run.scenario_id.slice(0, 8)}
                  </span>
                )}
              </div>
            </label>
          );
        })}
      </div>
    </div>
  );
}
