"use client";

import { Button } from "@/components/ui/button";
import { NetworkGraphDialog } from "@/components/nodal/network-graph-dialog";
import { getTopologyNetwork, scrapeTopology } from "@/lib/api-client";
import { NODAL_EXAMPLE_NETWORK } from "@/lib/nodal-example";
import type { NodalNetwork } from "@/lib/types";
import { useT } from "@/lib/i18n-context";
import { useMemo, useState } from "react";

interface ValidationResult {
  network: NodalNetwork | null;
  errors: string[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function validateNodalNetwork(raw: string): ValidationResult {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return { network: null, errors: ["jsonInvalid"] };
  }
  if (!isRecord(parsed)) {
    return { network: null, errors: ["jsonInvalid"] };
  }

  const errors: string[] = [];

  const zones = parsed.zones;
  if (
    !Array.isArray(zones) ||
    zones.length === 0 ||
    !zones.every((z) => isRecord(z) && typeof z.name === "string")
  ) {
    errors.push("zonesRequired");
  }
  const zoneNames = new Set(
    (Array.isArray(zones) ? zones : [])
      .filter((z): z is Record<string, unknown> => isRecord(z) && typeof z.name === "string")
      .map((z) => z.name as string)
  );

  if (typeof parsed.reference_zone !== "string" || !zoneNames.has(parsed.reference_zone)) {
    errors.push("referenceZoneInvalid");
  }

  const generators = Array.isArray(parsed.generators) ? parsed.generators : [];
  for (const g of generators) {
    if (
      !isRecord(g) ||
      typeof g.name !== "string" ||
      typeof g.zone !== "string" ||
      !zoneNames.has(g.zone) ||
      typeof g.p_max !== "number" ||
      typeof g.marginal_cost !== "number"
    ) {
      errors.push("generatorInvalid");
    }
  }

  const branches = Array.isArray(parsed.branches) ? parsed.branches : [];
  for (const b of branches) {
    if (
      !isRecord(b) ||
      typeof b.name !== "string" ||
      typeof b.from_zone !== "string" ||
      !zoneNames.has(b.from_zone) ||
      typeof b.to_zone !== "string" ||
      !zoneNames.has(b.to_zone) ||
      typeof b.reactance !== "number" ||
      typeof b.rating !== "number"
    ) {
      errors.push("branchInvalid");
    }
  }

  const loads = Array.isArray(parsed.loads) ? parsed.loads : [];
  for (const l of loads) {
    if (
      !isRecord(l) ||
      typeof l.zone !== "string" ||
      !zoneNames.has(l.zone) ||
      !Array.isArray(l.p_load) ||
      l.p_load.length !== 24 ||
      !l.p_load.every((v) => typeof v === "number")
    ) {
      errors.push("loadInvalid");
    }
  }

  const demandShares = parsed.demand_shares;
  if (
    demandShares !== undefined &&
    demandShares !== null &&
    Object.keys(demandShares as Record<string, unknown>).length > 0
  ) {
    const shares = demandShares as Record<string, unknown>;
    const shareKeys = new Set(Object.keys(shares));
    const coversZones = shareKeys.size === zoneNames.size && [...zoneNames].every((z) => shareKeys.has(z));
    const sum = Object.values(shares).reduce(
      (acc: number, v) => acc + (typeof v === "number" ? v : 0),
      0
    );
    if (!coversZones || Math.abs(sum - 1.0) > 1e-6) {
      errors.push("demandSharesInvalid");
    }
  }

  if (errors.length > 0) {
    return { network: null, errors };
  }

  const network: NodalNetwork = {
    name: typeof parsed.name === "string" ? parsed.name : "network",
    baseMVA: typeof parsed.baseMVA === "number" ? parsed.baseMVA : 100,
    reference_zone: parsed.reference_zone as string,
    zones: zones as NodalNetwork["zones"],
    generators: generators as NodalNetwork["generators"],
    branches: branches as NodalNetwork["branches"],
    loads: loads as NodalNetwork["loads"],
    demand_shares: (parsed.demand_shares ?? {}) as Record<string, number>,
  };
  return { network, errors: [] };
}

export function NodalNetworkEditor({
  value,
  onChange,
}: {
  value: NodalNetwork | null;
  onChange: (network: NodalNetwork | null) => void;
}) {
  const t = useT();
  const [text, setText] = useState(() => (value ? JSON.stringify(value, null, 2) : ""));
  const result = useMemo(() => validateNodalNetwork(text), [text]);
  const valid = result.errors.length === 0;
  const [colombiaStatus, setColombiaStatus] = useState<"idle" | "loading" | "scraping">("idle");
  const [colombiaError, setColombiaError] = useState<string | null>(null);

  function handleTextChange(next: string) {
    setText(next);
    onChange(validateNodalNetwork(next).network);
  }

  function loadExample() {
    setText(JSON.stringify(NODAL_EXAMPLE_NETWORK, null, 2));
    onChange(NODAL_EXAMPLE_NETWORK);
  }

  async function loadColombianNetwork() {
    setColombiaStatus("loading");
    setColombiaError(null);
    try {
      const { network } = await getTopologyNetwork();
      setText(JSON.stringify(network, null, 2));
      onChange(network);
    } catch (err) {
      setColombiaError((err as Error).message);
    } finally {
      setColombiaStatus("idle");
    }
  }

  async function scrapeAndLoadColombianNetwork() {
    setColombiaStatus("scraping");
    setColombiaError(null);
    try {
      await scrapeTopology(new Date().toISOString().slice(0, 10));
      await loadColombianNetwork();
    } catch (err) {
      setColombiaError((err as Error).message);
      setColombiaStatus("idle");
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <textarea
        id="nodal_network_json"
        value={text}
        onChange={(e) => handleTextChange(e.target.value)}
        placeholder={t("nodalNetwork.jsonPlaceholder")}
        spellCheck={false}
        className="h-56 w-full rounded-lg border border-input bg-transparent px-2.5 py-2 font-mono text-xs leading-relaxed text-foreground outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
      />
      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" variant="outline" size="sm" onClick={loadExample}>
          {t("nodalNetwork.example")}
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={loadColombianNetwork}
          disabled={colombiaStatus !== "idle"}
        >
          {colombiaStatus === "loading" ? t("nodalNetwork.loading") : t("nodalNetwork.loadColombia")}
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={scrapeAndLoadColombianNetwork}
          disabled={colombiaStatus !== "idle"}
        >
          {colombiaStatus === "scraping" ? t("nodalNetwork.scraping") : t("nodalNetwork.scrapeColombia")}
        </Button>
        <NetworkGraphDialog network={result.network} />
        <p
          className={
            valid
              ? "text-xs font-medium text-emerald-500"
              : "text-xs font-medium text-red-500"
          }
        >
          {valid ? t("nodalNetwork.valid") : t("nodalNetwork.invalid")}
        </p>
      </div>
      {colombiaError && (
        <p role="alert" className="text-xs text-red-400">
          {colombiaError}
        </p>
      )}
      {!valid && result.errors.length > 0 && (
        <div
          role="alert"
          className="rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2"
        >
          <p className="text-xs font-medium text-red-400">{t("nodalNetwork.errors")}</p>
          <ul className="mt-1 list-disc pl-4 text-xs text-red-400">
            {result.errors.map((code) => (
              <li key={code}>{t(`nodalNetwork.error.${code}`)}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}