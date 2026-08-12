"use client";

import { Button } from "@/components/ui/button";
import { downloadRunArtifact } from "@/lib/api-client";
import type { RunArtifacts } from "@/lib/types";
import { useT } from "@/lib/i18n-context";
import { Download } from "lucide-react";
import { useState } from "react";

type ArtifactKey = keyof RunArtifacts;

const ARTIFACT_LABEL_KEYS: Record<ArtifactKey, string> = {
  dispatch: "artifacts.dispatch",
  prices: "artifacts.prices",
  bess: "artifacts.bess",
};

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

  const available = (Object.keys(artifacts) as ArtifactKey[]).filter(
    (key) => artifacts[key]
  );

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
