"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NodalNetworkEditor } from "@/components/nodal-network-editor";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { createRun, listScenarios } from "@/lib/api-client";
import type { CreateRunRequest, DispatchLevel, NodalNetwork } from "@/lib/types";
import { useT } from "@/lib/i18n-context";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import {
  Calendar,
  Cpu,
  Layers,
  Network,
  Play,
  Workflow,
} from "lucide-react";

export function CreateRunForm({ onCreated }: { onCreated: () => void }) {
  const [dispatchDate, setDispatchDate] = useState("");
  const [level, setLevel] = useState<DispatchLevel>("preideal");
  const [solver, setSolver] = useState("cbc");
  const [scenarioId, setScenarioId] = useState("");
  const [network, setNetwork] = useState<NodalNetwork | null>(null);
  const router = useRouter();
  const t = useT();

  const scenariosQuery = useQuery({ queryKey: ["scenarios"], queryFn: listScenarios });
  const mutation = useMutation({
    mutationFn: (variables: CreateRunRequest) => createRun(variables),
    onSuccess: (data) => {
      router.push(`/runs/${data.run_id}`);
      onCreated();
    },
  });

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    mutation.mutate({
      dispatch_date: dispatchDate,
      level,
      solver,
      scenario_id: scenarioId || null,
      nodal_network: level === "lmp" ? network : null,
    });
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="dispatch_date" className="flex items-center gap-1.5">
            <Calendar className="size-3.5 text-muted-foreground" />
            {t("createRun.date")}
          </Label>
          <Input
            id="dispatch_date"
            type="date"
            value={dispatchDate}
            onChange={(e) => setDispatchDate(e.target.value)}
            required
          />
          <p className="text-[0.7rem] text-muted-foreground">
            {t("createRun.dateHelp")}
          </p>
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="level" className="flex items-center gap-1.5">
            <Layers className="size-3.5 text-muted-foreground" />
            {t("createRun.level")}
          </Label>
          <Select
            value={level}
            onValueChange={(value) => setLevel(value as DispatchLevel)}
          >
            <SelectTrigger id="level">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="preideal">preideal</SelectItem>
              <SelectItem value="ideal">ideal</SelectItem>
              <SelectItem value="lmp">lmp</SelectItem>
            </SelectContent>
          </Select>
          <p className="text-[0.7rem] text-muted-foreground">
            {t("createRun.levelHelp")}
          </p>
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="solver" className="flex items-center gap-1.5">
            <Cpu className="size-3.5 text-muted-foreground" />
            {t("createRun.solver")}
          </Label>
          <Select
            value={solver}
            onValueChange={(value) => value && setSolver(value)}
          >
            <SelectTrigger id="solver">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="cbc">CBC</SelectItem>
              <SelectItem value="highs" disabled>
                HiGHS ({t("createRun.comingSoon")})
              </SelectItem>
            </SelectContent>
          </Select>
          <p className="text-[0.7rem] text-muted-foreground">
            {t("createRun.solverHelp")}
          </p>
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="scenario_id" className="flex items-center gap-1.5">
            <Workflow className="size-3.5 text-muted-foreground" />
            {t("createRun.scenario")}
          </Label>
          <Select
            value={scenarioId}
            onValueChange={(value) => value && setScenarioId(value)}
          >
            <SelectTrigger id="scenario_id">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="">{t("createRun.none")}</SelectItem>
              {(scenariosQuery.data ?? []).map((s) => (
                <SelectItem key={s.id} value={s.id}>
                  {s.penetration_level} ({s.mode})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-[0.7rem] text-muted-foreground">
            {t("createRun.scenarioHelp")}
          </p>
        </div>

        <Button
          type="submit"
          disabled={mutation.isPending || (level === "lmp" && !network)}
          className="bg-amber-500 text-black hover:bg-amber-400 w-full sm:w-auto"
        >
          <Play className="size-3.5" />
          {mutation.isPending ? t("createRun.creating") : t("createRun.submit")}
        </Button>
      </div>

      {level === "lmp" && (
        <div className="flex flex-col gap-3 rounded-lg border border-border p-4">
          <div className="flex flex-col gap-1">
            <Label htmlFor="nodal_network_json" className="flex items-center gap-1.5">
              <Network className="size-3.5 text-muted-foreground" />
              {t("createRun.nodalNetwork")}
            </Label>
            <p className="text-[0.7rem] text-muted-foreground">
              {t("createRun.nodalNetworkHelp")}
            </p>
          </div>
          <NodalNetworkEditor value={network} onChange={setNetwork} />
          {!network && (
            <p className="text-xs text-red-400">{t("createRun.nodalNetworkRequired")}</p>
          )}
        </div>
      )}

      {mutation.isError && (
        <p
          role="alert"
          className="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-2 text-sm text-red-400"
        >
          {(mutation.error as Error).message}
        </p>
      )}
    </form>
  );
}
