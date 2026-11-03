from datetime import date
from enum import Enum

from pydantic import BaseModel

from app.schemas.bess import BessScenario


class DispatchLevel(str, Enum):
    preideal = "preideal"
    ideal = "ideal"
    lmp = "lmp"


class DispatchCase(BaseModel):
    dispatch_date: date
    level: DispatchLevel
    bess_scenario: BessScenario | None = None
    solver: str = "appsi_highs"
    compute_prices: bool = True
    nodal_network: str | None = None
    # Solo nivel ideal: fija las termicas a su generacion real (Gene) como
    # inflexibilidades (ver app/pipeline/thermal_fix.py). Dato ex post.
    thermal_real_generation: bool = False
