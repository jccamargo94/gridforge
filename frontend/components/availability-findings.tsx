"use client";

import { useT } from "@/lib/i18n-context";
import type { AvailabilityCheckResponse } from "@/lib/types";

export function AvailabilityFindings({ data }: { data: AvailabilityCheckResponse }) {
  const t = useT();
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm">
        {t("availability.coverage")}: {data.matched}/{data.resources_in_dispo} (
        {(data.match_rate * 100).toFixed(0)}%)
      </p>
      {data.findings.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("availability.none")}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-muted-foreground">
                <th>{t("availability.resource")}</th>
                <th>{t("availability.capacity")}</th>
                <th>{t("availability.issues")}</th>
                <th>{t("availability.maxRatio")}</th>
                <th>{t("availability.lowRun")}</th>
                <th>{t("availability.outage")}</th>
                <th>{t("availability.zeroHours")}</th>
              </tr>
            </thead>
            <tbody>
              {data.findings.map((f) => (
                <tr key={f.resource}>
                  <td>{f.resource}</td>
                  <td>{f.capacity_mw}</td>
                  <td>{f.issues.map((i) => t(`availability.issue.${i}`)).join(", ") || "-"}</td>
                  <td>{f.max_ratio_to_capacity}</td>
                  <td>{f.longest_low_run_days}</td>
                  <td>{f.outage_days}</td>
                  <td>{f.zero_hours.join(", ") || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data.unmatched_resources.length > 0 && (
        <p className="text-xs text-muted-foreground">
          {t("availability.unmatched")}: {data.unmatched_resources.length}
        </p>
      )}
    </div>
  );
}
