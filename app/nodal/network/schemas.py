from __future__ import annotations

import math

from pydantic import BaseModel, Field, model_validator


class Zone(BaseModel):
    name: str
    base_kv: float = 230.0


class Generator(BaseModel):
    name: str
    zone: str
    p_min: float = 0.0
    p_max: float
    marginal_cost: float
    no_load_cost: float = 0.0
    fuel: str = "thermal"
    min_up_time: int = 1
    min_down_time: int = 1
    initial_status: int = 0
    ramp_rate: float | None = None


class Branch(BaseModel):
    name: str
    from_zone: str
    to_zone: str
    reactance: float
    rating: float


class BusLoad(BaseModel):
    zone: str
    p_load: list[float] = Field(min_length=24, max_length=24)


class NodalNetwork(BaseModel):
    name: str = "network"
    baseMVA: float = 100.0
    reference_zone: str
    zones: list[Zone]
    generators: list[Generator]
    branches: list[Branch]
    loads: list[BusLoad] = []
    demand_shares: dict[str, float] = {}

    @model_validator(mode="after")
    def _validate_references(self) -> "NodalNetwork":
        zone_names = {z.name for z in self.zones}
        if self.reference_zone not in zone_names:
            raise ValueError(f"reference_zone '{self.reference_zone}' is not a zone")
        for g in self.generators:
            if g.zone not in zone_names:
                raise ValueError(f"generator '{g.name}' zone '{g.zone}' is not a zone")
        for b in self.branches:
            if b.from_zone not in zone_names:
                raise ValueError(f"branch '{b.name}' from_zone '{b.from_zone}' is not a zone")
            if b.to_zone not in zone_names:
                raise ValueError(f"branch '{b.name}' to_zone '{b.to_zone}' is not a zone")
        for load in self.loads:
            if load.zone not in zone_names:
                raise ValueError(f"load zone '{load.zone}' is not a zone")
        if self.demand_shares:
            if set(self.demand_shares) != zone_names:
                raise ValueError("demand_shares must cover exactly the network zones")
            if not math.isclose(sum(self.demand_shares.values()), 1.0, abs_tol=1e-6):
                raise ValueError("demand_shares must sum to 1.0")
        return self
