from pydantic import BaseModel

from app.schemas.case import DispatchCase
from app.schemas.nodal_run_result import NodalRunResult


class RunResult(BaseModel):
    case: DispatchCase
    ok: bool
    dispatch_path: str | None = None
    price_path: str | None = None
    bess_path: str | None = None
    bess_summary: dict[str, float] | None = None
    metrics_path: str | None = None
    metrics: dict[str, float] | None = None
    marginal_plants_path: str | None = None
    error: str | None = None
    nodal: NodalRunResult | None = None
