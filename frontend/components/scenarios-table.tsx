import type { Scenario } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatBogotaTime } from "@/lib/format-date";
import { useT } from "@/lib/i18n-context";

const MODE_COLORS: Record<string, string> = {
  arbitrage: "bg-blue-500/10 text-blue-400",
  grid_asset: "bg-emerald-500/10 text-emerald-400",
  generator: "bg-amber-500/10 text-amber-400",
};

export function ScenariosTable({ scenarios }: { scenarios: Scenario[] }) {
  const t = useT();

  if (scenarios.length === 0)
    return (
      <p className="text-sm text-muted-foreground">
        {t("scenariosTable.empty")}
      </p>
    );

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{t("scenariosTable.penetration")}</TableHead>
          <TableHead>{t("scenariosTable.mode")}</TableHead>
          <TableHead>{t("scenariosTable.units")}</TableHead>
          <TableHead>{t("scenariosTable.created")}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {scenarios.map((s) => (
          <TableRow key={s.id} className="hover:bg-accent/50">
            <TableCell>{s.penetration_level}</TableCell>
            <TableCell>
              <Badge className={MODE_COLORS[s.mode] ?? ""}>{s.mode}</Badge>
            </TableCell>
            <TableCell>{s.units.length}</TableCell>
            <TableCell>{formatBogotaTime(s.created_at)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
