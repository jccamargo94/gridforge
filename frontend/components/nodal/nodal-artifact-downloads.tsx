"use client";

import { useState } from "react";
import { Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { downloadNodalArtifact } from "@/lib/api-client";
import { useT } from "@/lib/i18n-context";
import type { NodalArtifactName } from "@/lib/types";

const NODAL_ARTIFACTS: { name: NodalArtifactName; labelKey: string; ext: string }[] = [
  { name: "lmp", labelKey: "nodal.artifact.lmp", ext: ".csv" },
  { name: "dispatch", labelKey: "nodal.artifact.dispatch", ext: ".csv" },
  { name: "branch_flows", labelKey: "nodal.artifact.branch_flows", ext: ".csv" },
  { name: "settlement_status_quo", labelKey: "nodal.artifact.settlement_status_quo", ext: ".csv" },
  { name: "settlement_lmp", labelKey: "nodal.artifact.settlement_lmp", ext: ".csv" },
  { name: "comparison", labelKey: "nodal.artifact.comparison", ext: ".csv" },
  { name: "summary", labelKey: "nodal.artifact.summary", ext: ".json" },
];

interface NodalArtifactDownloadsProps {
  runId: string;
  artifacts: Record<NodalArtifactName, boolean>;
}

export function NodalArtifactDownloads({ runId, artifacts }: NodalArtifactDownloadsProps) {
  const t = useT();
  const [error, setError] = useState<string | null>(null);
  const available = NODAL_ARTIFACTS.filter((artifact) => artifacts[artifact.name]);

  const handleDownload = async (name: NodalArtifactName, ext: string) => {
    try {
      setError(null);
      const blob = await downloadNodalArtifact(runId, name);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${name}-${runId}${ext}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      setError(t("artifacts.downloadError"));
    }
  };

  if (available.length === 0) {
    return <p className="text-sm text-muted-foreground">{t("artifacts.noData")}</p>;
  }

  return (
    <div>
      <div className="flex flex-wrap gap-2">
        {available.map((artifact) => (
          <Button key={artifact.name} variant="outline" size="sm"
            onClick={() => handleDownload(artifact.name, artifact.ext)}>
            <Download className="size-3.5" />
            {t(artifact.labelKey)}
          </Button>
        ))}
      </div>
      {error && <p role="alert" className="mt-3 text-sm text-red-400">{error}</p>}
    </div>
  );
}