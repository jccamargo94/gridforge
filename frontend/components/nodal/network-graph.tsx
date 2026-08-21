"use client";

import {
  Background,
  Controls,
  Handle,
  Position,
  ReactFlow,
  applyNodeChanges,
  type Edge,
  type Node,
  type NodeProps,
  type OnNodesChange,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { ChevronRight, Star } from "lucide-react";
import { useCallback, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { formatNumber } from "@/lib/chart-format";
import { useT } from "@/lib/i18n-context";
import type { NodalBranch, NodalGenerator, NodalNetwork } from "@/lib/types";

export interface ZoneNodeData extends Record<string, unknown> {
  zoneName: string;
  installedCapacityMw: number;
  peakDemandMw: number;
  generatorCount: number;
  isReference: boolean;
  /** Truncated display label; present on collapsed pills only. */
  displayName?: string;
}

export interface BranchEdgeData extends Record<string, unknown> {
  branchName: string;
  reactance: number;
  rating: number;
}

export type ZoneFlowNode = Node<ZoneNodeData, "zonePill" | "zoneCard">;
export type BranchFlowEdge = Edge<BranchEdgeData>;

/** Minimum pairwise center distance between zone nodes, in px. */
export const ZONE_LAYOUT_SPACING = 180;

const PILL_NAME_MAX_LENGTH = 14;

function peakLoadMw(network: NodalNetwork, zone: string): number {
  const load = network.loads.find((l) => l.zone === zone);
  if (!load || load.p_load.length === 0) return 0;
  return Math.max(...load.p_load);
}

/**
 * Deterministic ring layout sized for card/pill-sized nodes: adjacent centers
 * end up at least ZONE_LAYOUT_SPACING apart regardless of zone count. Owned by
 * the graph because lib/nodal-layout's ring is sized for small SVG circles and
 * zonal-map depends on that contract. The first zone sits at the top (-90deg)
 * and the rest follow at fixed 360/n steps.
 */
export function computeGraphLayout(
  zoneNames: string[],
): Record<string, { x: number; y: number }> {
  const n = zoneNames.length;
  if (n === 0) return {};
  if (n === 1) return { [zoneNames[0]]: { x: 0, y: 0 } };

  const radiusFromSpacing = ZONE_LAYOUT_SPACING / (2 * Math.sin(Math.PI / n));
  // Floor for tiny polygons (n <= 3): the spacing formula alone yields a ring
  // smaller than the spacing itself, which reads as a collapsed cluster.
  const radius =
    n <= 3 ? Math.max(radiusFromSpacing, ZONE_LAYOUT_SPACING) : radiusFromSpacing;

  const positions: Record<string, { x: number; y: number }> = {};
  zoneNames.forEach((name, i) => {
    const angle = (2 * Math.PI * i) / n - Math.PI / 2;
    positions[name] = {
      x: radius * Math.cos(angle),
      y: radius * Math.sin(angle),
    };
  });
  return positions;
}

/** Pure helper: ellipsis-terminated truncation capped at maxLength characters. */
export function truncateName(name: string, maxLength: number): string {
  if (name.length <= maxLength) return name;
  return `${name.slice(0, Math.max(0, maxLength - 1))}…`;
}

/**
 * Pure mapping from a validated NodalNetwork to React Flow elements.
 * Kept free of rendering concerns so it can be unit-tested directly.
 * At most one node (expandedId) becomes a full card; the rest stay pills.
 * Positions depend only on the zone list, never on expandedId.
 */
export function buildGraphElements(
  network: NodalNetwork,
  expandedId?: string | null,
): {
  nodes: ZoneFlowNode[];
  edges: BranchFlowEdge[];
} {
  const layout = computeGraphLayout(network.zones.map((z) => z.name));

  const nodes: ZoneFlowNode[] = network.zones.map((zone) => {
    const generators = network.generators.filter((g) => g.zone === zone.name);
    const isExpanded = zone.name === expandedId;
    return {
      id: zone.name,
      type: isExpanded ? "zoneCard" : "zonePill",
      position: layout[zone.name] ?? { x: 0, y: 0 },
      data: {
        zoneName: zone.name,
        installedCapacityMw: generators.reduce((sum, g) => sum + g.p_max, 0),
        peakDemandMw: peakLoadMw(network, zone.name),
        generatorCount: generators.length,
        isReference: zone.name === network.reference_zone,
        ...(isExpanded
          ? {}
          : { displayName: truncateName(zone.name, PILL_NAME_MAX_LENGTH) }),
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

function ZonePillNode({ data }: NodeProps<ZoneFlowNode>) {
  const t = useT();
  const ariaLabel = data.isReference
    ? `${t("nodalNetwork.graph.expandZone")}: ${data.zoneName} (${t("nodalNetwork.graph.referenceZone")})`
    : `${t("nodalNetwork.graph.expandZone")}: ${data.zoneName}`;
  return (
    <div data-zone-node={data.zoneName} className="flex h-8 items-center">
      {/* Clicks bubble to React Flow's node handler, which owns the accordion
          toggle; the button exists so keyboard users get it for free. */}
      <button
        type="button"
        title={data.zoneName}
        aria-label={ariaLabel}
        className={`flex h-8 w-[124px] cursor-pointer items-center gap-1 rounded-full bg-card px-2.5 text-card-foreground shadow-sm ring-1 transition-shadow hover:shadow-md ${
          data.isReference ? "ring-2 ring-primary" : "ring-foreground/10"
        }`}
      >
        {data.isReference && (
          <Star
            className="h-3.5 w-3.5 shrink-0 fill-amber-400 text-amber-500"
            aria-hidden
          />
        )}
        <span className="truncate text-xs font-medium">
          {data.displayName ?? data.zoneName}
        </span>
        <ChevronRight
          className="ml-auto h-3.5 w-3.5 shrink-0 text-muted-foreground"
          aria-hidden
        />
      </button>
      <Handle type="target" position={Position.Bottom} />
      <Handle type="source" position={Position.Top} />
    </div>
  );
}

function ZoneCardNode({ data }: NodeProps<ZoneFlowNode>) {
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
          <dd className="font-medium text-foreground">
            {formatNumber(data.installedCapacityMw, 1)}
          </dd>
        </div>
        <div className="flex items-center justify-between gap-3">
          <dt>{t("nodalNetwork.graph.peakDemand")}</dt>
          <dd className="font-medium text-foreground">
            {formatNumber(data.peakDemandMw, 1)}
          </dd>
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

const nodeTypes = { zonePill: ZonePillNode, zoneCard: ZoneCardNode };

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
        <span className="font-medium text-foreground">
          {formatNumber(detail.peakDemandMw, 1)}
        </span>
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
                {t("nodalNetwork.graph.marginalCost")}: {formatNumber(g.marginal_cost, 2)}
              </p>
              <p className="text-muted-foreground">
                {t("nodalNetwork.graph.pMax")}: {formatNumber(g.p_max, 1)}
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
                {t("nodalNetwork.graph.reactance")}: {formatNumber(b.reactance, 4)}
              </p>
              <p className="text-muted-foreground">
                {t("nodalNetwork.graph.rating")}: {formatNumber(b.rating, 1)}
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
  // Nodes live in state so drags persist across expand/collapse.
  const [nodes, setNodes] = useState<ZoneFlowNode[]>(() =>
    buildGraphElements(network).nodes,
  );
  // Reset-on-prop-change during render (see react.dev "You Might Not Need an
  // Effect"): a live JSON edit rebuilds elements fresh from the new network --
  // the layout reset is intentional, dragged positions do not carry over.
  const [prevNetwork, setPrevNetwork] = useState(network);
  if (prevNetwork !== network) {
    setPrevNetwork(network);
    setNodes(buildGraphElements(network).nodes);
  }

  const onNodesChange: OnNodesChange<ZoneFlowNode> = useCallback(
    (changes) => setNodes((current) => applyNodeChanges(changes, current)),
    [],
  );

  // Variant flip only: positions come straight from state, so expanding or
  // collapsing never moves a node and dragged positions survive.
  const displayNodes = useMemo(
    () =>
      nodes.map((node) =>
        node.id === selectedZone && node.type === "zonePill"
          ? { ...node, type: "zoneCard" as const }
          : node,
      ),
    [nodes, selectedZone],
  );

  // Session-only view state: edge labels appear on hover or selection and are
  // never persisted anywhere.
  const visibleEdges = useMemo(
    () =>
      buildGraphElements(network).edges.map((edge) =>
        edge.id === activeEdgeId && edge.data
          ? {
              ...edge,
              label: `${formatNumber(edge.data.reactance, 4)} / ${formatNumber(edge.data.rating, 1)} MW`,
              labelStyle: { fill: "var(--foreground)", fontSize: 11 },
              labelBgStyle: { fill: "var(--card)", fillOpacity: 0.9 },
            }
          : edge,
      ),
    [network, activeEdgeId],
  );

  return (
    <div className="flex h-[480px] w-full overflow-hidden rounded-lg border border-border">
      <div className="relative h-full flex-1">
        <ReactFlow
          nodes={displayNodes}
          edges={visibleEdges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          nodeOrigin={[0.5, 0.5]}
          fitView
          nodesDraggable
          onNodeClick={(_, node) =>
            setSelectedZone((current) => (current === node.id ? null : node.id))
          }
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
