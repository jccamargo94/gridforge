"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useT } from "@/lib/i18n-context";
import type { MeritPositionResponse } from "@/lib/types";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const fmt = (n: number | null | undefined) =>
  n === null || n === undefined ? "-" : n.toLocaleString("en-US", { maximumFractionDigits: 1 });

export function MeritPositionView({ data }: { data: MeritPositionResponse }) {
  const t = useT();
  const rows = data.hours.flatMap((h) =>
    h.own.map((o) => ({ ...o, hour: h.hour, demand_mw: h.demand_mw })),
  );
  if (rows.length === 0) {
    return <p className="text-sm text-muted-foreground">{t("market.notFound")}</p>;
  }
  const firstResource = rows[0].resource;
  const chartData = rows
    .filter((r) => r.resource === firstResource)
    .map((r) => ({ hour: r.hour, cum_ahead_mw: r.cum_ahead_mw, demand_mw: r.demand_mw }));
  // Technology aggregates are the same shape every hour; show the midday hour.
  const midday = data.hours[12] ?? data.hours[0];

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle>
            {t("market.chartTitle")} - {firstResource}
          </CardTitle>
        </CardHeader>
        <CardContent className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="hour" />
              <YAxis width={60} />
              <Tooltip />
              <Line type="monotone" dataKey="cum_ahead_mw" name={t("market.cumAhead")} stroke="#3b82f6" dot={false} />
              <Line type="monotone" dataKey="demand_mw" name={t("market.demand")} stroke="#f59e0b" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("market.ownByHour")}</CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-muted-foreground">
                <th>{t("market.hour")}</th>
                <th>{t("market.resource")}</th>
                <th>{t("market.rank")}</th>
                <th>{t("market.cumAhead")}</th>
                <th>{t("market.demand")}</th>
                <th>{t("market.price")}</th>
                <th>{t("market.inMerit")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={`${r.resource}-${r.hour}`}>
                  <td>{r.hour}</td>
                  <td>{r.resource}</td>
                  <td>{r.rank}</td>
                  <td>{fmt(r.cum_ahead_mw)}</td>
                  <td>{fmt(r.demand_mw)}</td>
                  <td>{fmt(r.price_cop_mwh)}</td>
                  <td>{r.in_merit ? t("market.yes") : t("market.no")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("market.byTech")}</CardTitle>
          <p className="text-xs text-muted-foreground">{t("market.byTechHint")}</p>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-muted-foreground">
                <th>{t("market.tech")}</th>
                <th>{t("market.nResources")}</th>
                <th>{t("market.capacity")}</th>
                <th>{t("market.avgPrice")}</th>
                <th>{t("market.inMeritMw")}</th>
              </tr>
            </thead>
            <tbody>
              {midday.market_by_tech.map((m) => (
                <tr key={m.gen_type}>
                  <td>{m.gen_type}</td>
                  <td>{m.n_resources}</td>
                  <td>{fmt(m.capacity_mw)}</td>
                  <td>{fmt(m.avg_price_cop_mwh)}</td>
                  <td>{fmt(m.in_merit_mw)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 text-xs text-muted-foreground">
            {t("market.unpriced")}: {fmt(data.unpriced_mw_avg)}
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
