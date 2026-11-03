"use client";

import { useT } from "@/lib/i18n-context";
import type { OfferAuditResult } from "@/lib/types";
import { cn } from "@/lib/utils";

const fmt = (n: number | null | undefined) =>
  n === null || n === undefined ? "-" : n.toLocaleString("en-US", { maximumFractionDigits: 1 });

const FLAG_STYLE: Record<string, string> = {
  ok: "bg-emerald-500/15 text-emerald-400",
  warn: "bg-amber-500/15 text-amber-400",
  alert: "bg-red-500/15 text-red-400",
  changed: "bg-red-500/15 text-red-400",
};

export function OfferAuditTable({ results }: { results: OfferAuditResult[] }) {
  const t = useT();
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-muted-foreground">
            <th>{t("offerAudit.resource")}</th>
            <th>{t("offerAudit.price")}</th>
            <th>{t("offerAudit.source")}</th>
            <th>{t("offerAudit.flag")}</th>
            <th>{t("offerAudit.z")}</th>
            <th>{t("offerAudit.band")}</th>
            <th>{t("offerAudit.change")}</th>
            <th>{t("offerAudit.history")}</th>
          </tr>
        </thead>
        <tbody>
          {results.map((r, i) => (
            <tr key={`${r.resource}-${i}`}>
              <td>{r.resource}</td>
              {r.status === "no_offer" ? (
                <td colSpan={7}>{t("offerAudit.noOffer")}</td>
              ) : (
                <>
                  <td>{fmt(r.price_cop_mwh)}</td>
                  <td>
                    {r.price_source === "published" ? t("offerAudit.published") : t("offerAudit.candidate")}
                  </td>
                  {r.status === "insufficient_history" ? (
                    <td colSpan={5}>{t("offerAudit.insufficient")}</td>
                  ) : (
                    <>
                      <td>
                        <span className={cn("rounded px-2 py-0.5 text-xs", FLAG_STYLE[r.flag ?? "ok"])}>
                          {t(`offerAudit.flag.${r.flag ?? "ok"}`)}
                        </span>
                      </td>
                      <td>{r.z === null || r.z === undefined ? "-" : r.z.toFixed(2)}</td>
                      <td>
                        {fmt(r.band?.p05_cop_mwh)} - {fmt(r.band?.p95_cop_mwh)}
                      </td>
                      <td>
                        {r.change_vs_last_pct === null || r.change_vs_last_pct === undefined
                          ? "-"
                          : `${r.change_vs_last_pct}%`}
                      </td>
                      <td>{r.n_history}</td>
                    </>
                  )}
                </>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
