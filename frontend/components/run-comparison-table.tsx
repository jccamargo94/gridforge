import type { RunDetail, RunMetrics } from "@/lib/types";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { useT } from "@/lib/i18n-context";
import { formatNumber } from "@/lib/chart-format";

const METRIC_ROWS: { key: keyof RunMetrics; label: string }[] = [
  { key: "rmse", label: "RMSE" },
  { key: "mae", label: "MAE" },
  { key: "bias", label: "Bias" },
  { key: "wape", label: "WAPE" },
  { key: "smape", label: "sMAPE" },
  { key: "r2", label: "R2" },
  { key: "bess_charge_mwh", label: "BESS carga (MWh)" },
  { key: "bess_discharge_mwh", label: "BESS descarga (MWh)" },
  { key: "bess_avg_soc_mwh", label: "BESS SOC promedio (MWh)" },
  { key: "bess_net_revenue", label: "BESS ingreso neto" },
];

type BestDirection = "lowest" | "highest" | null;

function getDirection(key: keyof RunMetrics): BestDirection {
  switch (key) {
    case "rmse":
    case "mae":
    case "bias":
    case "wape":
    case "smape":
      return "lowest";
    case "r2":
      return "highest";
    default:
      return null;
  }
}

function formatValue(key: keyof RunMetrics, val: number | null): string {
  if (val === null) return "\u2014";
  switch (key) {
    case "rmse":
    case "mae":
    case "bias":
    case "wape":
    case "smape":
      return formatNumber(val, 2);
    case "r2":
      return formatNumber(val, 3);
    case "bess_charge_mwh":
    case "bess_discharge_mwh":
    case "bess_avg_soc_mwh":
      return formatNumber(val, 2);
    case "bess_net_revenue":
      return formatNumber(val, 2);
    default:
      return String(val);
  }
}

function getValues(
  runs: RunDetail[],
  key: keyof RunMetrics
): (number | null)[] {
  return runs.map((r) => r.metrics?.[key] ?? null);
}

function isBestValue(
  key: keyof RunMetrics,
  val: number | null,
  allVals: (number | null)[]
): boolean {
  if (val === null) return false;
  const direction = getDirection(key);
  if (direction === null) return false;
  const numeric = allVals.filter((v): v is number => v !== null);
  if (numeric.length < 2) return false;
  const best =
    direction === "lowest"
      ? Math.min(...numeric)
      : Math.max(...numeric);
  return val === best;
}

function isWorstValue(
  key: keyof RunMetrics,
  val: number | null,
  allVals: (number | null)[]
): boolean {
  if (val === null) return false;
  const direction = getDirection(key);
  if (direction === null) return false;
  const numeric = allVals.filter((v): v is number => v !== null);
  if (numeric.length < 2) return false;
  const worst =
    direction === "lowest"
      ? Math.max(...numeric)
      : Math.min(...numeric);
  return val === worst;
}

export function RunComparisonTable({ runs }: { runs: RunDetail[] }) {
  const t = useT();

  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t("compare.metric")}</TableHead>
            {runs.map((run) => (
              <TableHead key={run.run_id}>
                <div className="flex flex-col">
                  <span className="font-medium">
                    {run.dispatch_date} ({run.level})
                  </span>
                  {run.scenario_id && (
                    <span className="text-xs font-normal text-muted-foreground">
                      {run.scenario_id.slice(0, 8)}
                    </span>
                  )}
                  {run.metrics === null && (
                    <span className="text-xs font-normal text-muted-foreground">
                      ({t("compare.noMetrics")})
                    </span>
                  )}
                </div>
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {METRIC_ROWS.map((row) => {
            const allVals = getValues(runs, row.key);
            return (
              <TableRow key={row.key}>
                <TableCell className="font-medium">{row.label}</TableCell>
                {runs.map((run) => {
                  const val = run.metrics?.[row.key] ?? null;
                  const best = isBestValue(row.key, val, allVals);
                  const worst = isWorstValue(row.key, val, allVals);
                  return (
                    <TableCell
                      key={run.run_id}
                      className={cn(
                        val === null && "text-muted-foreground",
                        best && "text-emerald-400 font-medium",
                        worst && "text-red-400"
                      )}
                    >
                      {formatValue(row.key, val)}
                    </TableCell>
                  );
                })}
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
