"use client";

import {
  Background,
  Controls,
  Handle,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { useT } from "@/lib/i18n-context";
import { computeZoneLayout } from "@/lib/nodal-layout";
import type { NodalBranch, NodalGenerator, NodalNetwork } from "@/lib/types";

export interface ZoneNodeData extends Record<string, unknown> {
  zoneName: string;
  installedCapacityMw: number;
  peakDemandMw: number;
  generatorCount: number;
  isReference: boolean;
}

export interface BranchEdgeData extends Record<string, unknown> {
  branchName: string;
  reactance: number;
  rating: number;
}

export type ZoneFlowNode = Node<ZoneNodeData, "zone">;
export type BranchFlowEdge = Edge<BranchEdgeData>;

function peakLoadMw(network: NodalNetwork, zone: string): number {
  const load = network.loads.find((l) => l.zone === zone);
  if (!load || load.p_load.length === 0) return 0;
  return Math.max(...load.p_load);
}

/**
 * Pure mapping from a validated NodalNetwork to React Flow elements.
 * Kept free of rendering concerns so it can be unit-tested directly.
 */
export function buildGraphElements(network: NodalNetwork): {
  nodes: ZoneFlowNode[];
  edges: BranchFlowEdge[];
} {
  const layout = computeZoneLayout(network.zones.map((z) => z.name));

  const nodes: ZoneFlowNode[] = network.zones.map((zone) => {
    const generators = network.generators.filter((g) => g.zone === zone.name);
    return {
      id: zone.name,
      type: "zone",
      position: layout.positions[zone.name] ?? { x: 0, y: 0 },
      data: {
        zoneName: zone.name,
        installedCapacityMw: generators.reduce((sum, g) => sum + g.p_max, 0),
        peakDemandMw: peakLoadMw(network, zone.name),
        generatorCount: generators.length,
        isReference: zone.name === network.reference_zone,
      },
    };
  });

  const edges: BranchFlowEdge[] = network.branches.map((branch) => ({
    id: branch.name,
    source: branch.from_zone,
    target: branch.to_zone,
    data: {
      branchName: branch.name,
      reactance: branch.reactance,
      rating: branch.rating,
    },
  }));

  return { nodes, edges };
}

function ZoneNode({ data }: NodeProps<ZoneFlowNode>) {
  const t = useT();
  return (
    <div
      data-zone-node={data.zoneName}
      className="min-w-[150px] rounded-xl bg-card px-3 py-2 text-card-foreground ring-1 ring-foreground/10"
    >
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-semibold">{data.zoneName}</p>
        {data.isReference && (
          <Badge variant="secondary">{t("nodalNetwork.graph.referenceZone")}</Badge>
        )}
      </div>
      <dl className="mt-1 space-y-0.5 text-xs text-muted-foreground">
        <div className="flex items-center justify-between gap-3">
          <dt>{t("nodalNetwork.graph.installedCapacity")}</dt>
          <dd className="font-medium text-foreground">{data.installedCapacityMw}</dd>
        </div>
        <div className="flex items-center justify-between gap-3">
          <dt>{t("nodalNetwork.graph.peakDemand")}</dt>
          <dd className="font-medium text-foreground">{data.peakDemandMw}</dd>
        </div>
        <div className="flex items-center justify-between gap-3">
          <dt>{t("nodalNetwork.graph.generators")}</dt>
          <dd className="font-medium text-foreground">{data.generatorCount}</dd>
        </div>
      </dl>
      <Handle type="target" position={Position.Bottom} />
      <Handle type="source" position={Position.Top} />
    </div>
  );
}

const nodeTypes = { zone: ZoneNode };

interface ZoneDetail {
  generators: NodalGenerator[];
  branches: NodalBranch[];
  peakDemandMw: number;
}

function getZoneDetail(network: NodalNetwork, zone: string): ZoneDetail {
  return {
    generators: network.generators.filter((g) => g.zone === zone),
    branches: network.branches.filter(
      (b) => b.from_zone === zone || b.to_zone === zone,
    ),
    peakDemandMw: peakLoadMw(network, zone),
  };
}

function ZoneDetailPanel({
  network,
  zone,
}: {
  network: NodalNetwork;
  zone: string;
}) {
  const t = useT();
  const detail = getZoneDetail(network, zone);

  return (
    <aside
      aria-label={t("nodalNetwork.graph.zoneDetails")}
      className="w-72 shrink-0 overflow-y-auto border-l border-border p-3"
    >
      <h3 className="text-sm font-semibold">{zone}</h3>
      <p className="mt-1 text-xs text-muted-foreground">
        {t("nodalNetwork.graph.peakDemand")}:{" "}
        <span className="font-medium text-foreground">{detail.peakDemandMw}</span>
      </p>

      <h4 className="mt-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {t("nodalNetwork.graph.generators")}
      </h4>
      {detail.generators.length === 0 ? (
        <p className="mt-1 text-xs text-muted-foreground">
          {t("nodalNetwork.graph.noGenerators")}
        </p>
      ) : (
        <ul className="mt-1 space-y-1">
          {detail.generators.map((g) => (
            <li key={g.name} className="rounded-lg bg-muted/50 px-2 py-1.5 text-xs">
              <p className="font-medium text-foreground">{g.name}</p>
              <p className="text-muted-foreground">
                {t("nodalNetwork.graph.fuel")}: {g.fuel}
              </p>
              <p className="text-muted-foreground">
                {t("nodalNetwork.graph.marginalCost")}: {g.marginal_cost}
              </p>
              <p className="text-muted-foreground">
                {t("nodalNetwork.graph.pMax")}: {g.p_max}
              </p>
            </li>
          ))}
        </ul>
      )}

      <h4 className="mt-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {t("nodalNetwork.graph.branches")}
      </h4>
      {detail.branches.length === 0 ? (
        <p className="mt-1 text-xs text-muted-foreground">
          {t("nodalNetwork.graph.noBranches")}
        </p>
      ) : (
        <ul className="mt-1 space-y-1">
          {detail.branches.map((b) => (
            <li key={b.name} className="rounded-lg bg-muted/50 px-2 py-1.5 text-xs">
              <p className="font-medium text-foreground">
                {b.from_zone} → {b.to_zone}
              </p>
              <p className="text-muted-foreground">
                {t("nodalNetwork.graph.reactance")}: {b.reactance}
              </p>
              <p className="text-muted-foreground">
                {t("nodalNetwork.graph.rating")}: {b.rating}
              </p>
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}

export function NetworkGraph({ network }: { network: NodalNetwork }) {
  const t = useT();
  const [selectedZone, setSelectedZone] = useState<string | null>(null);
  const [activeEdgeId, setActiveEdgeId] = useState<string | null>(null);

  const { nodes, edges } = useMemo(() => buildGraphElements(network), [network]);

  // Session-only view state: edge labels appear on hover or selection and are
  // never persisted anywhere.
  const visibleEdges = useMemo(
    () =>
      edges.map((edge) =>
        edge.id === activeEdgeId && edge.data
          ? {
              ...edge,
              label: `${edge.data.reactance} / ${edge.data.rating} MW`,
              labelStyle: { fill: "var(--foreground)", fontSize: 11 },
              labelBgStyle: { fill: "var(--card)", fillOpacity: 0.9 },
            }
          : edge,
      ),
    [edges, activeEdgeId],
  );

  return (
    <div className="flex h-[480px] w-full overflow-hidden rounded-lg border border-border">
      <div className="relative h-full flex-1">
        <ReactFlow
          nodes={nodes}
          edges={visibleEdges}
          nodeTypes={nodeTypes}
          fitView
          nodesDraggable
          onNodeClick={(_, node) => setSelectedZone(node.id)}
          onPaneClick={() => setSelectedZone(null)}
          onEdgeMouseEnter={(_, edge) => setActiveEdgeId(edge.id)}
          onEdgeMouseLeave={() => setActiveEdgeId(null)}
          onEdgeClick={(_, edge) => setActiveEdgeId(edge.id)}
          proOptions={{ hideAttribution: true }}
          aria-label={`${t("nodalNetwork.graph.dialogTitle")} ${network.name}`}
        >
          <Background />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
      {selectedZone && <ZoneDetailPanel network={network} zone={selectedZone} />}
    </div>
  );
}
