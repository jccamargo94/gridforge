export type RunStatus = "pending" | "running" | "done" | "failed";
export type DispatchLevel = "preideal" | "ideal" | "lmp";

export interface RunSummary {
  run_id: string;
  status: RunStatus;
  dispatch_date: string;
  level: DispatchLevel;
  scenario_id: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  nodal: NodalSummary | null;
}

export interface RunMetrics {
  rmse: number | null;
  mae: number | null;
  bias: number | null;
  wape: number | null;
  smape: number | null;
  r2: number | null;
  dispatch_mae_mw: number | null;
  dispatch_rmse_mw: number | null;
  bess_charge_mwh: number | null;
  bess_discharge_mwh: number | null;
  bess_avg_soc_mwh: number | null;
  bess_net_revenue: number | null;
}

export interface PricePoint {
  datetime: string;
  model_mpo: number;
  xm_mpo: number;
}

export interface MarginalPlant {
  datetime: string;
  generador: string;
  dispatch: number;
  pmax: number;
  is_marginal: boolean;
}

export interface DispatchRow {
  generador: string;
  datetime: string;
  dispatch: number;
}

export interface RunArtifacts {
  dispatch: boolean;
  prices: boolean;
  bess: boolean;
  marginal_plants: boolean;
}

export interface RunDetail extends Omit<RunSummary, "nodal"> {
  metrics: RunMetrics | null;
  artifacts: RunArtifacts;
  price_series: PricePoint[] | null;
  nodal: NodalResult | null;
}

export type BessMode = "arbitrage" | "grid_asset" | "generator";

export interface BessUnit {
  name: string;
  mwh_nom: number;
  hours_to_deplete: number;
  initial_soc: number;
  min_soc: number;
  max_soc: number;
  efficiency: number;
  charge_bid?: number | null;
  discharge_bid?: number | null;
}

export interface Scenario {
  id: string;
  mode: BessMode;
  penetration_level: string;
  units: BessUnit[];
  created_at: string;
}

export interface CreateScenarioRequest {
  mode: "arbitrage" | "grid_asset";
  penetration_level: string;
  units: BessUnit[];
}

export interface CreateRunRequest {
  dispatch_date: string;
  level: DispatchLevel;
  solver?: string;
  compute_prices?: boolean;
  scenario_id?: string | null;
  nodal_network?: NodalNetwork | null;
  recompute_demand_shares?: boolean;
}

export interface NodalSummary {
  network_name: string | null;
  zones: number;
  generators: number;
  branches: number;
}

export type NodalArtifactName =
  | "lmp" | "dispatch" | "branch_flows"
  | "settlement_status_quo" | "settlement_lmp" | "comparison" | "summary";

export interface NodalZone { name: string; base_kv: number; }

export interface NodalGenerator {
  name: string; zone: string; p_min: number; p_max: number;
  marginal_cost: number; no_load_cost: number; fuel: string;
  min_up_time: number; min_down_time: number; initial_status: number;
  ramp_rate: number | null;
}

export interface NodalBranch {
  name: string; from_zone: string; to_zone: string;
  reactance: number; rating: number;
}

export interface NodalBusLoad { zone: string; p_load: number[]; }

export interface NodalNetwork {
  name: string; baseMVA: number; reference_zone: string;
  zones: NodalZone[]; generators: NodalGenerator[]; branches: NodalBranch[];
  loads: NodalBusLoad[]; demand_shares: Record<string, number>;
}

export interface TopologyNetworkResponse {
  network: NodalNetwork;
  scraped_at: string | null;
}

export interface TopologyScrapeResponse {
  zones: number;
  generators: number;
  branches: number;
}

export type NodalMetrics = Record<string, number>;

export interface NodalRedistributionRow {
  zone: string; load_payment_a: number; load_payment_b: number; delta: number;
}

export interface NodalGenRevenueRow {
  zone: string; fuel: string; revenue_a: number; revenue_b: number; delta: number;
}

export interface NodalResult {
  metrics: NodalMetrics;
  redistribution: NodalRedistributionRow[];
  gen_revenue_by_zone: NodalGenRevenueRow[];
  network: NodalNetwork;
  price_series: PricePoint[] | null;
  artifacts: Record<NodalArtifactName, boolean>;
}

export interface LmpRow {
  timestamp: string; bus: string; lmp: number;
  lmp_avg: number; lmp_congestion: number;
}

export interface NodalDispatchRow {
  generator: string; zone: string; fuel: string; hour: number; dispatch_mw: number;
}

export interface BranchFlowRow { timestamp: string; branch: string; flow_mw: number; }

export interface SettlementRow {
  zone: string; hour: number; load_payment: number; gen_revenue: number;
  uplift?: number | null;
}

export interface NodalSummaryTotals {
  total_cost: number; total_load_payment_a: number; total_load_payment_b: number;
  total_gen_revenue_a: number; total_gen_revenue_b: number; congestion_rent_total: number;
}

export interface NodalSummaryJson {
  metrics: NodalMetrics; totals: NodalSummaryTotals;
  generator_count: number; branch_count: number;
}
