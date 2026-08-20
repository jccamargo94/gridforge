"use client";

import { Dialog } from "@base-ui/react/dialog";
import dynamic from "next/dynamic";
import { Button } from "@/components/ui/button";
import { useT } from "@/lib/i18n-context";
import type { NodalNetwork } from "@/lib/types";

// React Flow is only needed once the user opens the graph, so keep it out of
// the main bundle via a client-side dynamic import.
const NetworkGraph = dynamic(
  () => import("./network-graph").then((m) => m.NetworkGraph),
  { ssr: false },
);

export function NetworkGraphDialog({ network }: { network: NodalNetwork | null }) {
  const t = useT();

  return (
    <Dialog.Root>
      <Dialog.Trigger
        disabled={!network}
        render={<Button type="button" variant="outline" size="sm" />}
      >
        {t("nodalNetwork.graph.viewGraph")}
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Backdrop className="fixed inset-0 z-40 bg-black/50" />
        <Dialog.Popup className="fixed left-1/2 top-1/2 z-50 flex max-h-[90vh] w-[min(960px,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 flex-col rounded-xl bg-background p-4 shadow-lg ring-1 ring-foreground/10 outline-none">
          <div className="flex items-center justify-between gap-3">
            <Dialog.Title className="text-base font-semibold">
              {t("nodalNetwork.graph.dialogTitle")}
            </Dialog.Title>
            <Dialog.Close
              render={
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  aria-label={t("nodalNetwork.graph.close")}
                />
              }
            >
              ✕
            </Dialog.Close>
          </div>
          <div className="mt-3 min-h-0 flex-1 overflow-y-auto">
            {network ? <NetworkGraph network={network} /> : null}
          </div>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
