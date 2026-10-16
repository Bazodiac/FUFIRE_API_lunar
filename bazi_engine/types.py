from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional, Sequence

from .constants import BRANCHES, STEMS

TimeStandard = Literal["CIVIL", "LMT", "TLST"]
DayBoundary = Literal["midnight", "zi"]
EphemerisBackendName = Literal["swisseph", "skyfield"]
Fold = Literal[0, 1]

@dataclass(frozen=True)
class Pillar:
    stem_index: int
    branch_index: int
    def __str__(self) -> str:
        return f"{STEMS[self.stem_index]}{BRANCHES[self.branch_index]}"

@dataclass(frozen=True)
class FourPillars:
    year: Pillar
    month: Pillar
    day: Pillar
    hour: Pillar

@dataclass(frozen=True)
class SolarTerm:
    index: int
    target_lon_deg: float
    utc_dt: datetime
    local_dt: datetime

@dataclass(frozen=True)
class BaziInput:
    birth_local: str
    timezone: str
    longitude_deg: float
    latitude_deg: float
    time_standard: TimeStandard = "CIVIL"
    day_boundary: DayBoundary = "midnight"
    ephemeris_backend: EphemerisBackendName = "swisseph"
    accuracy_seconds: float = 1.0

    strict_local_time: bool = True
    fold: Fold = 0

    ephe_path: Optional[str] = None

    # v0.4 Configurable Day Anchor
    day_anchor_date_iso: Optional[str] = None
    day_anchor_pillar_idx: Optional[int] = None
    
    # v0.4 Month Boundary Scheme.
    # FBP-02-006 (Phase 2): vestigial — never read by compute_bazi().
    # Kept for backward-compat with v1 consumers; non-default values
    # emit a DeprecationWarning at the engine entry. Slated for
    # removal in /v2 once consumers stop sending the field.
    month_boundary_scheme: Literal["jie_only", "all_24"] = "jie_only"

@dataclass(frozen=True)
class BaziResult:
    input: BaziInput
    pillars: FourPillars

    birth_local_dt: datetime
    birth_utc_dt: datetime
    chart_local_dt: datetime

    jd_ut: float
    jd_tt: float
    delta_t_seconds: float

    lichun_local_dt: datetime
    month_boundaries_local_dt: Sequence[datetime]
    month_index: int

    # v1.0 Transition metadata — clarifies year boundary at LiChun
    solar_year: int = 0
    is_before_lichun: bool = False
    lichun_next_local_dt: Optional[datetime] = None

    solar_terms_local_dt: Optional[Sequence[SolarTerm]] = None

    # FBP-TST-003 (GT6): the chart-local datetime whose calendar date the
    # engine actually used for the day pillar (after the midnight/zi
    # day-boundary policy, TLST-aware when applicable). Exposed so the
    # derivation trace reuses the engine's decision instead of re-deriving
    # it with a different rule. ``None`` only for results built outside
    # ``compute_bazi`` (back-compat); consumers must fall back explicitly.
    chart_day_dt: Optional[datetime] = None
