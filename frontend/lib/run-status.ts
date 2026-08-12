import { t as translate } from "./i18n";
import type { Lang } from "./i18n";
import type { RunStatus } from "./types";

export function isTerminalStatus(status: RunStatus): boolean {
  return status === "done" || status === "failed";
}

export function statusLabel(status: RunStatus, lang: Lang = "es"): string {
  switch (status) {
    case "pending":
      return translate(lang, "status.pending");
    case "running":
      return translate(lang, "status.running");
    case "done":
      return translate(lang, "status.done");
    case "failed":
      return translate(lang, "status.failed");
  }
}

type BadgeVariant = "default" | "secondary" | "outline" | "destructive";

const STATUS_BADGE_VARIANT: Record<RunStatus, BadgeVariant> = {
  pending: "outline",
  running: "secondary",
  done: "default",
  failed: "destructive",
};

export function statusBadgeVariant(status: RunStatus): BadgeVariant {
  return STATUS_BADGE_VARIANT[status];
}
