"use client";

import { Button } from "@/components/ui/button";
import { downloadRunArtifact } from "@/lib/api-client";
import type { RunArtifacts } from "@/lib/types";
import { useT } from "@/lib/i18n-context";
import { Download } from "lucide-react";
import { useState } from "react";

type ArtifactKey = "dispatch" | "prices" | "bess" | "marginal_plants" | "price_comparison";

const ARTIFACT_LABEL_KEYS: Record<ArtifactKey, string> = {
  dispatch: "artifacts.dispatch",
  prices: "artifacts.prices",
  bess: "artifacts.bess",
  marginal_plants: "artifacts.marginalPlants",
  price_comparison: "artifacts.priceComparison",
};

const ALL_ARTIFACTS: ArtifactKey[] = [
  "dispatch",
  "prices",
  "bess",
  "marginal_plants",
  "price_comparison",
];

function isAvailable(key: ArtifactKey, artifacts: RunArtifacts): boolean {
  if (key === "price_comparison") return artifacts.prices;
  return artifacts[key];
}

export function ArtifactDownloads({
  runId,
  artifacts,
}: {
  runId: string;
  artifacts: RunArtifacts;
}) {
  const [error, setError] = useState<string | null>(null);
  const t = useT();

  async function handleDownload(artifact: ArtifactKey) {
    setError(null);
    try {
      const blob = await downloadRunArtifact(runId, artifact);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${artifact}-${runId}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      setError(t("artifacts.downloadError"));
    }
  }

  const available = ALL_ARTIFACTS.filter((key) => isAvailable(key, artifacts));

  if (available.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        {t("artifacts.noData")}
      </p>
    );
  }

  return (
    <div>
      <div className="flex flex-wrap gap-3">
        {available.map((artifact) => (
          <Button
            key={artifact}
            variant="outline"
            size="sm"
            onClick={() => handleDownload(artifact)}
          >
            <Download className="size-3.5" />
            {t(ARTIFACT_LABEL_KEYS[artifact])}
          </Button>
        ))}
      </div>
      {error && (
        <p role="alert" className="mt-3 text-sm text-red-400">
          {error}
        </p>
      )}
    </div>
  );
}
