"""
routers/webhooks.py — POST /internal/api/webhooks/chart (ElevenLabs voice agent integration, internal only)
"""
from __future__ import annotations

import json
import os
from datetime import timezone
from typing import Any, Dict, List, Literal, Optional, cast

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from ..bazi import compute_bazi
from ..exc import BaziEngineError
from ..fusion import compute_fusion_analysis
from ..services.auth import verify_request_auth
from ..services.geocoding import geocode_place
from ..time_utils import LocalTimeError, resolve_local_iso
from ..types import BaziInput, Fold
from ..western import compute_western_chart
from .shared import ZODIAC_SIGNS_DE, format_pillar

router = APIRouter(prefix="/api", tags=["Webhooks"])


class ElevenLabsChartRequest(BaseModel):
    birthDate: str = Field(..., description="Birth date YYYY-MM-DD")
    birthTime: Optional[str] = Field(None, description="Birth time HH:MM (optional)")
    birthPlace: Optional[str] = Field(None, description="Place name, e.g. 'Berlin, DE'")
    birthLat: Optional[float] = None
    birthLon: Optional[float] = None
    birthTz: Optional[str] = None
    ambiguousTime: Literal["earlier", "later"] = "earlier"
    nonexistentTime: Literal["error", "shift_forward"] = "error"


ZODIAC_SIGNS_EN = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]


class WebhookWesternSection(BaseModel):
    sunSign: str
    moonSign: str
    sunSignEnglish: str
    moonSignEnglish: str
    ascendant: Optional[float] = None
    ascendantSign: Optional[str] = None
    ascendantDegreeInSign: Optional[float] = None
    retrogradePlanets: List[str] = []


class WebhookEasternSection(BaseModel):
    yearAnimal: str
    yearElement: str
    monthAnimal: str
    monthElement: str
    dayAnimal: str
    dayElement: str
    dayMaster: str
    hourAnimal: str
    hourElement: str


class WebhookFusionSection(BaseModel):
    harmonyIndex: float
    harmonyIndexRaw: Optional[float] = None
    harmonyInterpretation: str
    cosmicState: str
    westernDominantElement: str
    baziDominantElement: str
    wuXingWestern: Dict[str, float]
    wuXingBazi: Dict[str, float]
    elementalComparison: Dict[str, Any]
    interpretation: Dict[str, Any]


class WebhookSummary(BaseModel):
    sternzeichen: str
    mondzeichen: str
    chinesischesZeichen: str
    tagesmeister: str
    harmonie: str
    dominantesElement: str


class WebhookChartResponse(BaseModel):
    western: WebhookWesternSection
    eastern: WebhookEasternSection
    fusion: WebhookFusionSection
    summary: WebhookSummary
    meta: Dict[str, Any]


def _voice_fusion_summary(fusion: Dict[str, Any]) -> Dict[str, Any]:
    """Claim-safe fusion values for the ElevenLabs voice profile (FUF-147).

    The voice agent speaks these values to end users, so they must come from
    the calibrated model, never from the raw harmony index (raw H is
    empirically always ≥ 0.5 and would read as a positive judgment). The raw
    value is preserved separately as an expert diagnostic.
    """
    cal = fusion.get("calibration", {})
    h_calibrated = max(0.0, min(1.0, cal.get("h_calibrated", 0.5)))
    return {
        "harmonyIndex": h_calibrated,
        "harmonyIndexRaw": cal.get("h_raw"),
        "harmonyInterpretation": cal.get(
            "interpretation_band",
            "Kalibrierte Kohärenz nicht verfügbar — keine Aussage möglich",
        ),
        "harmonie": f"{h_calibrated:.0%}",
    }


@router.post("/webhooks/chart", response_model=WebhookChartResponse)
async def elevenlabs_chart_webhook(
    request: Request,
    elevenlabs_signature: Optional[str] = Header(None, alias="elevenlabs-signature"),
    x_api_key: Optional[str] = Header(None, alias="x-api-key"),
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """ElevenLabs Agent Tool: Astrology chart for a birth date."""
    tool_secret = os.environ.get("ELEVENLABS_TOOL_SECRET")
    if not tool_secret:
        raise HTTPException(status_code=503, detail={
            "error": "service_unavailable",
            "message": "Webhook service is not configured",
            "detail": {},
        })

    raw_body = await request.body()

    hmac_only = os.environ.get("WEBHOOK_HMAC_ONLY", "true").lower() in {"1", "true", "yes", "on"}
    if not verify_request_auth(
        raw_body,
        elevenlabs_signature=elevenlabs_signature,
        x_api_key=x_api_key,
        authorization=authorization,
        secret=tool_secret,
        hmac_only=hmac_only,
    ):
        raise HTTPException(status_code=401, detail={
            "error": "unauthorized",
            "message": "Invalid webhook authentication",
            "detail": {},
        })

    try:
        data = json.loads(raw_body)
        req = ElevenLabsChartRequest(**data)
    except Exception:
        raise HTTPException(status_code=400, detail={
            "error": "invalid_request",
            "message": "Request body is invalid or malformed",
            "detail": {},
        })

    # Resolve location
    geo_result = None
    lat, lon, tz = req.birthLat, req.birthLon, req.birthTz

    if req.birthPlace and (lat is None or lon is None or not tz):
        try:
            geo_result = await geocode_place(req.birthPlace)
            lat = lat if lat is not None else geo_result["lat"]
            lon = lon if lon is not None else geo_result["lon"]
            tz = tz or geo_result["timezone"]
        except Exception:
            raise HTTPException(status_code=400, detail={
                "error": "geocoding_failed",
                "message": "Could not resolve birth place. Check the place name and try again.",
                "detail": {},
            })

    lat = lat if lat is not None else 52.52
    lon = lon if lon is not None else 13.405
    tz = tz or "Europe/Berlin"

    assumed_time = req.birthTime is None
    birth_time = req.birthTime or "12:00"
    datetime_str = f"{req.birthDate}T{birth_time}:00"

    try:
        dt, time_res = resolve_local_iso(
            datetime_str, tz,
            ambiguous=req.ambiguousTime, nonexistent=req.nonexistentTime,
        )
        dt_utc = dt.astimezone(timezone.utc)

        western_chart = compute_western_chart(dt_utc, lat, lon)
        bodies = western_chart.get("bodies", {})
        sun = bodies.get("Sun", {})
        moon = bodies.get("Moon", {})

        sun_sign_idx  = int(sun.get("zodiac_sign", 0))
        moon_sign_idx = int(moon.get("zodiac_sign", 0))

        resolved_naive_iso = dt.replace(tzinfo=None).isoformat()
        inp = BaziInput(
            birth_local=resolved_naive_iso,
            timezone=tz,
            longitude_deg=lon,
            latitude_deg=lat,
            time_standard="CIVIL",
            day_boundary="midnight",
            strict_local_time=True,
            fold=cast(Fold, time_res.fold),
        )
        bazi_result = compute_bazi(inp)

        year_pillar  = format_pillar(bazi_result.pillars.year)
        month_pillar = format_pillar(bazi_result.pillars.month)
        day_pillar   = format_pillar(bazi_result.pillars.day)
        hour_pillar  = format_pillar(bazi_result.pillars.hour)

        bazi_pillars_for_fusion = {
            p: {"stamm": pil["stamm"], "zweig": pil["zweig"]}
            for p, pil in [
                ("year", year_pillar), ("month", month_pillar),
                ("day", day_pillar), ("hour", hour_pillar),
            ]
        }
        fusion = compute_fusion_analysis(
            birth_utc_dt=dt_utc, latitude=lat, longitude=lon,
            bazi_pillars=bazi_pillars_for_fusion, western_bodies=bodies,
        )

        voice_fusion = _voice_fusion_summary(fusion)
        retrogrades: List[str] = [n for n, b in bodies.items() if b.get("is_retrograde")]
        wu_xing = fusion["wu_xing_vectors"]
        western_dominant = max(wu_xing["western_planets"], key=lambda k: wu_xing["western_planets"][k])
        bazi_dominant    = max(wu_xing["bazi_pillars"],    key=lambda k: wu_xing["bazi_pillars"][k])

        asc_raw = western_chart.get("angles", {}).get("Ascendant")
        asc_sign = ZODIAC_SIGNS_DE[int(asc_raw // 30) % 12] if isinstance(asc_raw, (int, float)) else None
        asc_deg_in_sign = round(asc_raw % 30, 2) if isinstance(asc_raw, (int, float)) else None

        warnings: List[str] = []
        if assumed_time:
            warnings.append("Geburtszeit nicht angegeben: Ascendent/Häuser sind nur Näherung.")
        if time_res.warning:
            warnings.append(time_res.warning)

        return {
            "western": {
                "sunSign":             ZODIAC_SIGNS_DE[sun_sign_idx],
                "moonSign":            ZODIAC_SIGNS_DE[moon_sign_idx],
                "sunSignEnglish":      ZODIAC_SIGNS_EN[sun_sign_idx],
                "moonSignEnglish":     ZODIAC_SIGNS_EN[moon_sign_idx],
                "ascendant":           asc_raw,
                "ascendantSign":       asc_sign,
                "ascendantDegreeInSign": asc_deg_in_sign,
                "retrogradePlanets":   retrogrades,
            },
            "eastern": {
                "yearAnimal":   year_pillar["tier"],
                "yearElement":  year_pillar["element"],
                "monthAnimal":  month_pillar["tier"],
                "monthElement": month_pillar["element"],
                "dayAnimal":    day_pillar["tier"],
                "dayElement":   day_pillar["element"],
                "dayMaster":    day_pillar["stamm"],
                "hourAnimal":   hour_pillar["tier"],
                "hourElement":  hour_pillar["element"],
                "solarYear":    bazi_result.solar_year,
                "isBeforeLiChun": bazi_result.is_before_lichun,
                "lichunNext":   bazi_result.lichun_next_local_dt.isoformat() if bazi_result.lichun_next_local_dt else None,
            },
            "fusion": {
                # FUF-147: voice-facing values are calibrated; raw only as
                # labeled expert diagnostic (harmonyIndexRaw).
                "harmonyIndex":          voice_fusion["harmonyIndex"],
                "harmonyIndexRaw":       voice_fusion["harmonyIndexRaw"],
                "harmonyInterpretation": voice_fusion["harmonyInterpretation"],
                "cosmicState":           fusion["cosmic_state"],
                "westernDominantElement": western_dominant,
                "baziDominantElement":    bazi_dominant,
                "wuXingWestern":          wu_xing["western_planets"],
                "wuXingBazi":             wu_xing["bazi_pillars"],
                "elementalComparison":    fusion["elemental_comparison"],
                "interpretation":         fusion["fusion_interpretation"],
            },
            "summary": {
                "sternzeichen": ZODIAC_SIGNS_DE[sun_sign_idx],
                "mondzeichen":  ZODIAC_SIGNS_DE[moon_sign_idx],
                "chinesischesZeichen": f"{year_pillar['element']} {year_pillar['tier']}",
                "tagesmeister":        f"{day_pillar['element']} ({day_pillar['stamm']})",
                "harmonie":            voice_fusion["harmonie"],
                "dominantesElement":   f"West: {western_dominant}, Ost: {bazi_dominant}",
            },
            "meta": {
                "time": {
                    "inputLocal":      time_res.input_local_iso,
                    "resolvedLocal":   time_res.resolved_local_iso,
                    "resolvedUtc":     time_res.resolved_utc_iso,
                    "timezone":        time_res.tz,
                    "tzAbbrev":        time_res.tz_abbrev,
                    "status":          time_res.status,
                    "fold":            time_res.fold,
                    "adjustedMinutes": time_res.adjusted_minutes,
                    "assumedTime":     assumed_time,
                    "warnings":        warnings,
                },
                "location": {
                    "lat": lat, "lon": lon, "tz": tz,
                    "birthPlace": req.birthPlace, "geocoded": geo_result,
                },
            },
        }

    except LocalTimeError as e:
        raise HTTPException(status_code=422, detail={
            "error": "invalid_local_time",
            "message": str(e),
            "detail": {"hint": "The given birth time does not exist. Please provide a valid local time."},
        })
    except BaziEngineError:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail={
            "error": "calculation_error",
            "message": "Internal calculation error",
            "detail": {},
        })
