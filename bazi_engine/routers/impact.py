"""
routers/impact.py — POST /impact/active endpoint.

Computes natal-relative planet impacts with BaZi resonance, harmony index,
space weather, and coherence drivers for a given birth chart and target date.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from ..bazi import compute_bazi
from ..constants import STEMS
from ..exc import BaziEngineError
from ..impact import find_active_planets
from ..impact_harmony import (
    build_evidence,
    build_resonance_badges,
    classify_day_mode,
    compute_drivers,
    compute_harmony_index,
    compute_intensity,
    find_top_sector,
    natal_wuxing_vector,
    transit_wuxing_vector,
)
from ..impact_resonance import day_master_element, enrich_active_planets
from ..impact_types import ImpactRequest, ImpactResponse
from ..limiter import limiter, tier_limit
from ..services.space_weather import compute_space_weather_score, fetch_space_weather
from ..transit import compute_transit_now
from ..types import BaziInput
from ..western import compute_western_chart

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/impact", tags=["Impact"])


@router.post("/active", response_model=ImpactResponse)
@limiter.limit(tier_limit)
async def impact_active(
    request: Request,
    body: ImpactRequest,
) -> ImpactResponse:
    """Compute natal-relative planet impacts for a target date.

    Returns harmony index, active planets with BaZi resonance, space weather,
    coherence drivers, resonance badges, and calculation evidence.
    """
    birth = body.birth
    target = body.target_date or datetime.now(timezone.utc).date()

    # 1. Compute natal chart
    birth_iso = f"{birth.date}T{birth.time}"
    bazi_inp = BaziInput(
        birth_local=birth_iso,
        timezone=birth.tz,
        longitude_deg=birth.lon,
        latitude_deg=birth.lat,
        time_standard="CIVIL",  # v1/legacy contract (FU-TLST-POLICY/INC-1, decision A): same pillars as the /calculate/bazi default
    )
    try:
        bazi_result = compute_bazi(bazi_inp)
    except BaziEngineError:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": "computation_error", "message": f"BaZi calculation failed: {exc}"},
        )

    stem_name = STEMS[bazi_result.pillars.day.stem_index]
    master_elem = day_master_element(stem_name)

    # 2. Compute natal Western chart for planet positions
    birth_utc = bazi_result.birth_utc_dt
    try:
        western = compute_western_chart(birth_utc, birth.lat, birth.lon)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": "computation_error", "message": f"Western chart failed: {exc}"},
        )
    natal_bodies = western.get("bodies", {})
    house_cusps = western.get("houses", {})

    # 3. Compute transits for target date (noon UTC)
    target_dt = datetime(target.year, target.month, target.day, 12, 0, 0, tzinfo=timezone.utc)
    transit_data = compute_transit_now(dt_utc=target_dt)
    transit_planets = transit_data.get("planets", {})

    # 4. Find active planets (orb ≤ 8°, house-weighted)
    active = find_active_planets(natal_bodies, transit_planets, house_cusps)

    # 5. Enrich with BaZi resonance
    active = enrich_active_planets(active, master_elem)

    # 6. Fetch space weather
    space_weather, sw_partial = await fetch_space_weather()
    sw_score = compute_space_weather_score(space_weather)

    # 7. Compute harmony metrics
    natal_vec = natal_wuxing_vector(body.soulprint_sectors, body.quiz_sectors)
    transit_vec = transit_wuxing_vector(active)
    harmony = compute_harmony_index(natal_vec, transit_vec)
    intensity = compute_intensity(harmony, len(active), sw_score)
    mode = classify_day_mode(harmony, intensity)
    drivers = compute_drivers(sw_score, len(active), harmony)

    # 8. Build response
    return ImpactResponse(
        harmony_index=harmony,
        day_mode=mode,
        intensity=intensity,
        active_planets=active,
        space_weather=space_weather,
        space_weather_score=sw_score,
        drivers=drivers,
        resonance_badges=build_resonance_badges(active),
        top_sector=find_top_sector(active),
        day_master=master_elem,
        evidence=build_evidence(natal_vec, transit_vec, harmony),
        partial=sw_partial,
    )
