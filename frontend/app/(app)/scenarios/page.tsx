"use client";

import { CreateScenarioForm } from "@/components/create-scenario-form";
import { ScenariosTable } from "@/components/scenarios-table";
import { listScenarios } from "@/lib/api-client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useT } from "@/lib/i18n-context";
import { useQuery, useQueryClient } from "@tanstack/react-query";

export default function ScenariosPage() {
  const queryClient = useQueryClient();
  const scenariosQuery = useQuery({ queryKey: ["scenarios"], queryFn: listScenarios });
  const t = useT();

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-heading text-2xl font-bold">{t("scenarios.title")}</h1>
        <p className="text-sm text-muted-foreground">
          {t("scenarios.subtitle")}
        </p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>{t("scenarios.create")}</CardTitle>
        </CardHeader>
        <CardContent>
          <CreateScenarioForm
            onCreated={() => queryClient.invalidateQueries({ queryKey: ["scenarios"] })}
          />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>{t("scenarios.saved")}</CardTitle>
        </CardHeader>
        <CardContent>
          {scenariosQuery.isLoading && (
            <p className="text-sm text-muted-foreground">{t("scenarios.loading")}</p>
          )}
          {scenariosQuery.data && scenariosQuery.data.length === 0 && (
            <p className="text-sm text-muted-foreground">
              {t("scenarios.empty")}
            </p>
          )}
          {scenariosQuery.data && scenariosQuery.data.length > 0 && (
            <ScenariosTable scenarios={scenariosQuery.data} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
