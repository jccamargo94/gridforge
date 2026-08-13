"use client";

import type { MarginalPlant } from "@/lib/types";
import { useT } from "@/lib/i18n-context";
import { formatNumber } from "@/lib/chart-format";

function hourKey(datetime: string): string {
  const timePart = datetime.includes("T")
    ? (datetime.split("T")[1] ?? datetime)
    : (datetime.split(" ")[1] ?? datetime);
  const hh = timePart.split(":")[0] ?? "0";
  return `${hh.padStart(2, "0")}:00`;
}

export function MarginalPlantsTable({ rows }: { rows: MarginalPlant[] }) {
  const t = useT();

  const marginal = rows.filter((row) => row.is_marginal);

  if (marginal.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">{t("marginalPlants.empty")}</p>
    );
  }

  const groups = new Map<string, MarginalPlant[]>();
  for (const row of marginal) {
    const key = hourKey(row.datetime);
    const list = groups.get(key) ?? [];
    list.push(row);
    groups.set(key, list);
  }

  const hours = [...groups.keys()].sort();

  return (
    <div className="flex flex-col gap-6">
      {hours.map((hour) => (
        <div key={hour}>
          <h4 className="mb-2 text-sm font-semibold text-muted-foreground">
            {t("marginalPlants.hour")}: {hour}
          </h4>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs text-muted-foreground">
                <th className="py-1.5 pr-3 font-medium">{t("marginalPlants.generator")}</th>
                <th className="py-1.5 pr-3 text-right font-medium">
                  {t("marginalPlants.dispatch")}
                </th>
                <th className="py-1.5 text-right font-medium">{t("marginalPlants.pmax")}</th>
              </tr>
            </thead>
            <tbody>
              {(groups.get(hour) ?? []).map((row) => (
                <tr key={`${row.generador}-${row.datetime}`} className="border-b border-border/50">
                  <td className="py-1.5 pr-3">{row.generador}</td>
                  <td className="py-1.5 pr-3 text-right tabular-nums">
                    {formatNumber(row.dispatch, 2)}
                  </td>
                  <td className="py-1.5 text-right tabular-nums">{formatNumber(row.pmax, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}
