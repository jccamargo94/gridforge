"use client";

import { MarginalHeatmap } from "@/components/marginal-heatmap";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getMarginalMap } from "@/lib/api-client";
import { useT } from "@/lib/i18n-context";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

function daysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

export default function MarginalPage() {
  const t = useT();
  const [start, setStart] = useState(daysAgo(60));
  const [end, setEnd] = useState(daysAgo(31));
  const [tolPct, setTolPct] = useState("2");
  const [by, setBy] = useState<"tech" | "zone">("tech");
  const [submitted, setSubmitted] = useState<{ start: string; end: string; tol: number } | null>(null);

  const query = useQuery({
    queryKey: ["marginal-map", submitted],
    queryFn: () => getMarginalMap(submitted!.start, submitted!.end, submitted!.tol),
    enabled: submitted !== null,
    retry: false,
  });

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitted({ start, end, tol: Number(tolPct) / 100 });
  }

  const data = query.data;
  const hasZones = data?.zone_mapped_share !== null && data?.zone_mapped_share !== undefined;
  const pct = (v: number) => `${(v * 100).toFixed(1)}%`;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-heading text-2xl font-bold">{t("marginal.title")}</h1>
        <p className="text-sm text-muted-foreground">{t("marginal.subtitle")}</p>
      </div>
      <Card>
        <CardContent>
          <form onSubmit={onSubmit} className="flex flex-wrap items-end gap-4">
            <div className="flex flex-col gap-1">
              <Label htmlFor="mg-start">{t("marginal.start")}</Label>
              <Input id="mg-start" type="date" value={start} onChange={(e) => setStart(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="mg-end">{t("marginal.end")}</Label>
              <Input id="mg-end" type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="mg-tol">{t("marginal.tol")}</Label>
              <Input id="mg-tol" type="number" min={0} max={20} step={0.5} value={tolPct} onChange={(e) => setTolPct(e.target.value)} />
            </div>
            <Button type="submit">{t("marginal.run")}</Button>
          </form>
        </CardContent>
      </Card>
      {query.isFetching && <p className="text-sm text-muted-foreground">{t("marginal.loading")}</p>}
      {query.isError && (
        <p role="alert" className="rounded-lg border border-red-500/50 bg-red-500/10 p-3 text-sm text-red-400">
          {t("marginal.error")}
        </p>
      )}
      {data && !query.isFetching && (
        <Card>
          <CardContent className="flex flex-col gap-4">
            <div className="flex flex-wrap items-center gap-4 text-sm">
              <Button variant={by === "tech" ? "default" : "outline"} onClick={() => setBy("tech")}>
                {t("marginal.byTech")}
              </Button>
              <Button variant={by === "zone" ? "default" : "outline"} onClick={() => setBy("zone")} disabled={!hasZones}>
                {t("marginal.byZone")}
              </Button>
              <span>
                {t("marginal.attributed")}: {pct(data.attributed_share)}
              </span>
              <span>
                {t("marginal.ambiguous")}: {pct(data.ambiguous_share)}
              </span>
              {hasZones && (
                <span>
                  {t("marginal.zoneMapped")}: {pct(data.zone_mapped_share ?? 0)}
                </span>
              )}
            </div>
            {!hasZones && <p className="text-xs text-muted-foreground">{t("marginal.noZones")}</p>}
            {data.cells.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("marginal.empty")}</p>
            ) : (
              <MarginalHeatmap cells={data.cells} by={by} />
            )}
            <p className="text-xs text-muted-foreground">{t("marginal.hint")}</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
