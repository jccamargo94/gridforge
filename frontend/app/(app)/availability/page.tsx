"use client";

import { AvailabilityFindings } from "@/components/availability-findings";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getAvailabilityCheck } from "@/lib/api-client";
import { useT } from "@/lib/i18n-context";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

function daysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

export default function AvailabilityPage() {
  const t = useT();
  const [start, setStart] = useState(daysAgo(45));
  const [end, setEnd] = useState(daysAgo(1));
  const [submitted, setSubmitted] = useState<{ start: string; end: string } | null>(null);
  const query = useQuery({
    queryKey: ["availability-check", submitted],
    queryFn: () => getAvailabilityCheck(submitted!.start, submitted!.end),
    enabled: submitted !== null,
    retry: false,
  });

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-heading text-2xl font-bold">{t("availability.title")}</h1>
        <p className="text-sm text-muted-foreground">{t("availability.subtitle")}</p>
      </div>
      <Card>
        <CardContent>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setSubmitted({ start, end });
            }}
            className="flex flex-wrap items-end gap-4"
          >
            <div className="flex flex-col gap-1">
              <Label htmlFor="av-start">{t("availability.start")}</Label>
              <Input id="av-start" type="date" value={start} onChange={(e) => setStart(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="av-end">{t("availability.end")}</Label>
              <Input id="av-end" type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
            </div>
            <Button type="submit">{t("availability.run")}</Button>
          </form>
        </CardContent>
      </Card>
      {query.isFetching && <p className="text-sm text-muted-foreground">{t("availability.loading")}</p>}
      {query.isError && (
        <p role="alert" className="rounded-lg border border-red-500/50 bg-red-500/10 p-3 text-sm text-red-400">
          {t("availability.error")}
        </p>
      )}
      {query.data && !query.isFetching && <AvailabilityFindings data={query.data} />}
    </div>
  );
}
