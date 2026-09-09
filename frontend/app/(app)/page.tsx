"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { HomeChart } from "@/components/home-chart";
import { useChartSeries } from "@/hooks/use-chart-series";
import { useT } from "@/lib/i18n-context";
import { cn } from "@/lib/utils";

const WINDOWS = [7, 30, 90] as const;

export default function HomePage() {
  const t = useT();
  const [days, setDays] = useState<number>(30);
  const seriesQuery = useChartSeries(days);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl font-bold">{t("home.title")}</h1>
          <p className="text-sm text-muted-foreground">{t("home.subtitle")}</p>
        </div>
        <div
          role="group"
          aria-label={t("home.title")}
          className="flex items-center gap-1 rounded-full border border-zinc-800 p-1"
        >
          {WINDOWS.map((window) => (
            <button
              key={window}
              type="button"
              aria-pressed={days === window}
              onClick={() => setDays(window)}
              className={cn(
                "rounded-full px-3 py-1 text-sm tabular-nums transition-colors",
                days === window
                  ? "bg-amber-500/15 text-amber-400"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              {window}
            </button>
          ))}
        </div>
      </div>

      {seriesQuery.isLoading ? (
        <div className="flex items-center gap-3 py-8 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" />
          {t("home.loading")}
        </div>
      ) : seriesQuery.isError ? (
        <div
          role="alert"
          className="flex flex-col items-start gap-3 rounded-lg border border-red-900/50 bg-red-950/20 px-4 py-6 text-sm"
        >
          <p className="text-red-200">{t("home.error")}</p>
          <button
            type="button"
            onClick={() => seriesQuery.refetch()}
            className="rounded-full border border-zinc-700 px-3 py-1 text-zinc-200 transition-colors hover:border-zinc-500"
          >
            {t("home.retry")}
          </button>
        </div>
      ) : (
        <HomeChart rows={seriesQuery.data ?? null} />
      )}
    </div>
  );
}
