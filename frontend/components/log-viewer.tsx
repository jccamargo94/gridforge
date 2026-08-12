"use client";

import { useRunLog } from "@/hooks/use-run-log";
import { useT } from "@/lib/i18n-context";

export function LogViewer({ runId }: { runId: string }) {
  const { data, isLoading } = useRunLog(runId);
  const t = useT();

  if (isLoading) {
    return (
      <div className="rounded-lg border border-border bg-black p-4 font-mono text-xs text-emerald-400/60">
        {t("log.loading")}
      </div>
    );
  }

  if (!data) {
    return (
      <div className="rounded-lg border border-border bg-black p-4 font-mono text-xs text-emerald-400/60">
        {t("log.empty")}
      </div>
    );
  }

  return (
    <pre className="max-h-96 overflow-auto rounded-lg border border-border bg-black p-4 font-mono text-xs text-emerald-400">
      {data}
    </pre>
  );
}
