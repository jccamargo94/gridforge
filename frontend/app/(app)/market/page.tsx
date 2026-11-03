"use client";

import { MeritPositionView } from "@/components/merit-position-view";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getMeritPosition } from "@/lib/api-client";
import { useT } from "@/lib/i18n-context";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

function yesterday(): string {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  return d.toISOString().slice(0, 10);
}

export default function MarketPage() {
  const t = useT();
  const [date, setDate] = useState(yesterday());
  const [ownText, setOwnText] = useState("");
  const [submitted, setSubmitted] = useState<{ date: string; own: string[] } | null>(null);

  const query = useQuery({
    queryKey: ["merit-position", submitted],
    queryFn: () => getMeritPosition(submitted!.date, submitted!.own),
    enabled: submitted !== null,
    retry: false,
  });

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const own = ownText.split(",").map((s) => s.trim()).filter(Boolean);
    if (own.length > 0) setSubmitted({ date, own });
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-heading text-2xl font-bold">{t("market.title")}</h1>
        <p className="text-sm text-muted-foreground">{t("market.subtitle")}</p>
      </div>
      <Card>
        <CardContent>
          <form onSubmit={onSubmit} className="flex flex-wrap items-end gap-4">
            <div className="flex flex-col gap-1">
              <Label htmlFor="market-date">{t("market.date")}</Label>
              <Input id="market-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
            </div>
            <div className="flex min-w-64 flex-1 flex-col gap-1">
              <Label htmlFor="market-own">{t("market.own")}</Label>
              <Input
                id="market-own"
                value={ownText}
                placeholder={t("market.ownPlaceholder")}
                onChange={(e) => setOwnText(e.target.value)}
              />
            </div>
            <Button type="submit">{t("market.search")}</Button>
          </form>
        </CardContent>
      </Card>
      {query.isFetching && <p className="text-sm text-muted-foreground">{t("market.loading")}</p>}
      {query.isError && (
        <p role="alert" className="rounded-lg border border-red-500/50 bg-red-500/10 p-3 text-sm text-red-400">
          {t("market.error")}
        </p>
      )}
      {query.data && !query.isFetching && <MeritPositionView data={query.data} />}
    </div>
  );
}
