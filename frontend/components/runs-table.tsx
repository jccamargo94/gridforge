import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatBogotaTime, formatDuration } from "@/lib/format-date";
import { statusLabel } from "@/lib/run-status";
import { useLang, useT } from "@/lib/i18n-context";
import { cn } from "@/lib/utils";
import type { RunStatus, RunSummary } from "@/lib/types";
import { ArrowRight } from "lucide-react";
import Link from "next/link";

const STATUS_CLASSES: Record<RunStatus, string> = {
  pending: "bg-amber-500/10 text-amber-400 border border-amber-500/20",
  running: "bg-blue-500/10 text-blue-400 border border-blue-500/20",
  done: "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20",
  failed: "bg-red-500/10 text-red-400 border border-red-500/20",
};

export function RunsTable({ runs }: { runs: RunSummary[] }) {
  const { lang } = useLang();
  const t = useT();

  if (runs.length === 0) {
    return (
      <div className="flex flex-col items-center gap-3 py-12 text-center">
        <p className="text-sm text-muted-foreground">{t("runsTable.empty")}</p>
        <p className="text-xs text-muted-foreground/60">
          {t("runs.emptyHint")}
        </p>
      </div>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{t("runsTable.date")}</TableHead>
          <TableHead>{t("runsTable.level")}</TableHead>
          <TableHead>{t("runsTable.status")}</TableHead>
          <TableHead>{t("runsTable.created")}</TableHead>
          <TableHead>{t("runsTable.duration")}</TableHead>
          <TableHead />
        </TableRow>
      </TableHeader>
      <TableBody>
        {runs.map((run) => (
          <TableRow key={run.run_id} className="hover:bg-accent/50">
            <TableCell className="font-mono">{run.dispatch_date}</TableCell>
            <TableCell>{run.level}</TableCell>
            <TableCell>
              <span
                className={cn(
                  "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
                  STATUS_CLASSES[run.status]
                )}
              >
                {statusLabel(run.status, lang)}
              </span>
            </TableCell>
            <TableCell className="font-mono text-muted-foreground">
              {formatBogotaTime(run.created_at)}
            </TableCell>
            <TableCell className="font-mono text-muted-foreground">
              {formatDuration(run.started_at, run.finished_at)}
            </TableCell>
            <TableCell>
              <Link
                href={`/runs/${run.run_id}`}
                className="inline-flex items-center gap-1 text-sm font-medium text-amber-500 hover:text-amber-400"
              >
                {t("runsTable.view")}
                <ArrowRight className="size-3.5" />
              </Link>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
