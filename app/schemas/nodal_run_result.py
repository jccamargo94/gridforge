from pydantic import BaseModel


class NodalRunResult(BaseModel):
    lmp_path: str | None = None
    dispatch_path: str | None = None
    branch_flows_path: str | None = None
    settlement_status_quo_path: str | None = None
    settlement_lmp_path: str | None = None
    comparison_path: str | None = None
    summary_path: str | None = None
    metrics: dict[str, float] | None = None
    redistribution: list[dict] | None = None
    gen_revenue_by_zone: list[dict] | None = None
    network: dict | None = None
