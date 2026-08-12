"use client";

import { createScenario } from "@/lib/api-client";
import type { BessUnit, CreateScenarioRequest } from "@/lib/types";
import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useT } from "@/lib/i18n-context";
import { Plus, X } from "lucide-react";

function emptyUnit(): BessUnit {
  return {
    name: "",
    mwh_nom: 0,
    hours_to_deplete: 1,
    initial_soc: 0,
    min_soc: 0,
    max_soc: 0,
    efficiency: 0,
    charge_bid: null,
    discharge_bid: null,
  };
}

export function CreateScenarioForm({ onCreated }: { onCreated: () => void }) {
  const [mode, setMode] = useState<"arbitrage" | "grid_asset">("arbitrage");
  const [penetrationLevel, setPenetrationLevel] = useState("");
  const [units, setUnits] = useState<BessUnit[]>([emptyUnit()]);
  const t = useT();

  const mutation = useMutation({
    mutationFn: (variables: CreateScenarioRequest) => createScenario(variables),
    onSuccess: onCreated,
  });

  function updateUnit(index: number, patch: Partial<BessUnit>) {
    setUnits((prev) => prev.map((u, i) => (i === index ? { ...u, ...patch } : u)));
  }

  function addUnit() {
    setUnits((prev) => [...prev, emptyUnit()]);
  }

  function removeUnit(index: number) {
    setUnits((prev) => prev.filter((_, i) => i !== index));
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    mutation.mutate({ mode, penetration_level: penetrationLevel, units });
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-6">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="mode">{t("createScenario.mode")}</Label>
        <select
          id="mode"
          value={mode}
          onChange={(e) => setMode(e.target.value as "arbitrage" | "grid_asset")}
          className="h-8 w-full min-w-0 rounded-lg border border-input bg-transparent px-2.5 py-1 text-base transition-colors outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 md:text-sm dark:bg-input/30"
        >
          <option value="arbitrage">arbitrage</option>
          <option value="grid_asset">grid_asset</option>
        </select>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="penetration_level">{t("createScenario.penetrationLevel")}</Label>
        <Input
          id="penetration_level"
          value={penetrationLevel}
          onChange={(e) => setPenetrationLevel(e.target.value)}
          required
        />
      </div>

      <div className="flex flex-col gap-4">
        <Label>{t("createScenario.units")}</Label>
        {units.map((unit, i) => (
          <div key={i} className="border border-border rounded-lg p-4 bg-background">
            <div className="flex items-center justify-between mb-4">
              <span className="text-sm font-medium">{t("createScenario.unit")} {i + 1}</span>
              <Button type="button" variant="ghost" size="icon-xs" onClick={() => removeUnit(i)}>
                <X className="size-3" />
              </Button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor={`unit-${i}-name`}>{t("createScenario.name")}</Label>
                <Input
                  id={`unit-${i}-name`}
                  value={unit.name}
                  onChange={(e) => updateUnit(i, { name: e.target.value })}
                  required
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <Label htmlFor={`unit-${i}-mwh_nom`}>{t("createScenario.capacity")}</Label>
                <Input
                  id={`unit-${i}-mwh_nom`}
                  type="number"
                  step="any"
                  value={unit.mwh_nom}
                  onChange={(e) => updateUnit(i, { mwh_nom: Number(e.target.value) })}
                  required
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <Label htmlFor={`unit-${i}-hours_to_deplete`}>{t("createScenario.hoursToDeplete")}</Label>
                <Input
                  id={`unit-${i}-hours_to_deplete`}
                  type="number"
                  step="any"
                  min="0.01"
                  value={unit.hours_to_deplete}
                  onChange={(e) => updateUnit(i, { hours_to_deplete: Number(e.target.value) })}
                  required
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <Label htmlFor={`unit-${i}-initial_soc`}>{t("createScenario.initialSoc")}</Label>
                <Input
                  id={`unit-${i}-initial_soc`}
                  type="number"
                  step="any"
                  min="0"
                  max="1"
                  value={unit.initial_soc}
                  onChange={(e) => updateUnit(i, { initial_soc: Number(e.target.value) })}
                  required
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <Label htmlFor={`unit-${i}-min_soc`}>{t("createScenario.minSoc")}</Label>
                <Input
                  id={`unit-${i}-min_soc`}
                  type="number"
                  step="any"
                  min="0"
                  max="1"
                  value={unit.min_soc}
                  onChange={(e) => updateUnit(i, { min_soc: Number(e.target.value) })}
                  required
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <Label htmlFor={`unit-${i}-max_soc`}>{t("createScenario.maxSoc")}</Label>
                <Input
                  id={`unit-${i}-max_soc`}
                  type="number"
                  step="any"
                  min="0"
                  max="1"
                  value={unit.max_soc}
                  onChange={(e) => updateUnit(i, { max_soc: Number(e.target.value) })}
                  required
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <Label htmlFor={`unit-${i}-efficiency`}>{t("createScenario.efficiency")}</Label>
                <Input
                  id={`unit-${i}-efficiency`}
                  type="number"
                  step="any"
                  min="0"
                  max="1"
                  value={unit.efficiency}
                  onChange={(e) => updateUnit(i, { efficiency: Number(e.target.value) })}
                  required
                />
              </div>

              {mode === "arbitrage" && (
                <>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor={`unit-${i}-charge_bid`}>{t("createScenario.chargeBid")}</Label>
                    <Input
                      id={`unit-${i}-charge_bid`}
                      type="number"
                      step="any"
                      value={unit.charge_bid ?? ""}
                      onChange={(e) => updateUnit(i, { charge_bid: Number(e.target.value) })}
                      required
                    />
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor={`unit-${i}-discharge_bid`}>{t("createScenario.dischargeBid")}</Label>
                    <Input
                      id={`unit-${i}-discharge_bid`}
                      type="number"
                      step="any"
                      value={unit.discharge_bid ?? ""}
                      onChange={(e) => updateUnit(i, { discharge_bid: Number(e.target.value) })}
                      required
                    />
                  </div>
                </>
              )}
            </div>
          </div>
        ))}
      </div>

      <Button type="button" variant="outline" onClick={addUnit} className="text-sm">
        <Plus className="size-4" />
        {t("createScenario.addUnit")}
      </Button>

      <Button type="submit" disabled={mutation.isPending} className="w-full">
        {t("createScenario.submit")}
      </Button>

      {mutation.isError && (
        <p role="alert" className="rounded-lg border border-red-500/50 bg-red-500/10 p-3 text-sm text-red-400">
          {(mutation.error as Error).message}
        </p>
      )}
    </form>
  );
}
