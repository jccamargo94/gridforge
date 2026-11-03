"use client";

import { OfferAuditTable } from "@/components/offer-audit-table";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { auditOffers } from "@/lib/api-client";
import { parseOffers } from "@/lib/offer-parse";
import { useT } from "@/lib/i18n-context";
import type { OfferToAudit } from "@/lib/types";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export default function OffersPage() {
  const t = useT();
  const [date, setDate] = useState(today());
  const [windowDays, setWindowDays] = useState("90");
  const [text, setText] = useState("");
  const audit = useMutation({
    mutationFn: (offers: OfferToAudit[]) => auditOffers(date, offers, Number(windowDays)),
  });

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const offers = parseOffers(text);
    if (offers.length > 0) audit.mutate(offers);
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-heading text-2xl font-bold">{t("offerAudit.title")}</h1>
        <p className="text-sm text-muted-foreground">{t("offerAudit.subtitle")}</p>
      </div>
      <Card>
        <CardContent>
          <form onSubmit={onSubmit} className="flex flex-col gap-4">
            <div className="flex flex-wrap gap-4">
              <div className="flex flex-col gap-1">
                <Label htmlFor="audit-date">{t("offerAudit.date")}</Label>
                <Input id="audit-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="audit-window">{t("offerAudit.window")}</Label>
                <Input
                  id="audit-window"
                  type="number"
                  min={7}
                  max={365}
                  value={windowDays}
                  onChange={(e) => setWindowDays(e.target.value)}
                />
              </div>
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="audit-offers">{t("offerAudit.offers")}</Label>
              <textarea
                id="audit-offers"
                rows={6}
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder={"TERMO1, 320000\nTERMO2"}
                className="w-full rounded-lg border border-input bg-transparent p-2 font-mono text-sm"
              />
            </div>
            <div>
              <Button type="submit" disabled={audit.isPending}>
                {t("offerAudit.run")}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
      {audit.isPending && <p className="text-sm text-muted-foreground">{t("offerAudit.loading")}</p>}
      {audit.isError && (
        <p role="alert" className="rounded-lg border border-red-500/50 bg-red-500/10 p-3 text-sm text-red-400">
          {t("offerAudit.error")}
        </p>
      )}
      {audit.data && <OfferAuditTable results={audit.data} />}
    </div>
  );
}
