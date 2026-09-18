"""
routers/info.py — Informational and utility endpoints.

Endpoints: GET /, /health, /build, /api (zodiac lookup), /info/wuxing-mapping
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, Literal, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from starlette.responses import JSONResponse

from .. import __version__ as _ENGINE_VERSION
from ..ephemeris import SwissEphBackend
from ..exc import BaziEngineError
from ..fusion import PLANET_TO_WUXING, WUXING_ORDER
from ..limiter import get_storage_status
from ..time_utils import resolve_local_iso
from ..western import compute_western_chart
from .shared import ZODIAC_SIGNS_DE

router = APIRouter(tags=["Info"])

_BUILD_VERSION = os.environ.get("BUILD_VERSION", _ENGINE_VERSION)


# ── Response models ──────────────────────────────────────────────────────────

class RootResponse(BaseModel):
    status: str
    service: str
    version: str


class DependencyStatus(BaseModel):
    status: str  # "ok" | "degraded" | "unavailable"
    required: bool = True
    detail: Optional[str] = None


class HealthResponse(BaseModel):
    status: str  # "healthy" | "degraded" | "unavailable"
    engine: str = "FuFirE"
    version: str = ""
    dependencies: Dict[str, Any] = {}


class BuildResponse(BaseModel):
    version: str
    #: Provider-neutral, immutable source revision of the running build.
    #: A full 40-character lower-case git object id, or null when the platform
    #: did not supply one. Never a version string, tag or date.
    source_revision: Optional[str] = None
    #: Which deployment platform supplied `source_revision` ("northflank",
    #: "railway"). Null whenever `source_revision` is null.
    source_revision_provider: Optional[str] = None
    #: What kind of identity `source_revision` is ("deployment_git_sha").
    source_revision_kind: Optional[str] = None
    #: Why `source_revision` is what it is — "available", "unavailable"
    #: (no platform supplied one), "invalid" (a platform variable carried
    #: something that is not a full git object id) or "ambiguous" (several
    #: platforms claimed the deployment and none could be resolved).
    #: Fail-closed states never carry a revision.
    source_revision_status: str = "unavailable"
    railway_commit_sha: Optional[str] = None
    railway_deploy_id: Optional[str] = None
    fly_alloc_id: Optional[str] = None
    fly_region: Optional[str] = None


class ApiResponse(BaseModel):
    sonne: str
    input: Dict[str, Any]


class WuxingMappingResponse(BaseModel):
    mapping: Dict[str, Any]
    order: list
    description: Dict[str, str]


# ── Helpers ──────────────────────────────────────────────────────────────────

#: A git object id and nothing else: 40 lower-case hex characters. Branch names,
#: tags, abbreviated SHAs, semantic versions and dates are all reassignable and
#: are therefore never an immutable source revision.
_SOURCE_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")

#: Deployment platforms that hand the RUNNING container the git commit it was
#: built from. Each entry is
#:     (provider, revision variable, kind, marker variables)
#: where the revision variable and the markers are reserved names the platform
#: injects itself. The application never sets them, and FuFirE never presents
#: one platform's value under another platform's field name.
_SOURCE_REVISION_PROVIDERS: Tuple[Tuple[str, str, str, Tuple[str, ...]], ...] = (
    (
        "northflank",
        "NF_DEPLOYMENT_SHA",
        "deployment_git_sha",
        ("NF_OBJECT_ID", "NF_POD_ID", "NF_PROJECT_ID"),
    ),
    (
        "railway",
        "RAILWAY_GIT_COMMIT_SHA",
        "deployment_git_sha",
        ("RAILWAY_SERVICE_ID", "RAILWAY_PROJECT_ID", "RAILWAY_ENVIRONMENT_ID"),
    ),
)


def _unavailable(status: str) -> Dict[str, Optional[str]]:
    """A fail-closed source identity: a reason, never a substitute revision."""
    return {
        "source_revision": None,
        "source_revision_provider": None,
        "source_revision_kind": None,
        "source_revision_status": status,
    }


def _source_revision() -> Dict[str, Optional[str]]:
    """Resolve the immutable source revision of the build that is answering.

    The value comes from the deployment platform, never from an application
    environment value, so it cannot be forged by configuration. There is no
    plausible substitute: when the platform supplied nothing, supplied something
    that is not a git object id, or when several platforms claim the deployment
    and none can be resolved, the revision stays null and the status says why.
    """
    declared = [
        (provider, os.environ.get(variable, "").strip(), kind, markers)
        for provider, variable, kind, markers in _SOURCE_REVISION_PROVIDERS
    ]
    declared = [entry for entry in declared if entry[1]]

    if not declared:
        return _unavailable("unavailable")

    if any(not _SOURCE_REVISION_RE.match(value) for _, value, _, _ in declared):
        # A reserved deployment variable carrying something that is not a full
        # git object id is a misconfiguration. Reporting the other provider's
        # value here would hide it, so the whole identity fails closed.
        return _unavailable("invalid")

    if len(declared) > 1:
        # Several platforms claim this deployment. Resolve it only when exactly
        # one of them also injected its own marker variables; otherwise refuse
        # rather than pick silently.
        active = [
            entry
            for entry in declared
            if any(os.environ.get(marker, "").strip() for marker in entry[3])
        ]
        if len(active) != 1:
            return _unavailable("ambiguous")
        declared = active

    provider, value, kind, _ = declared[0]
    return {
        "source_revision": value,
        "source_revision_provider": provider,
        "source_revision_kind": kind,
        "source_revision_status": "available",
    }


def _build_metadata() -> Dict[str, Any]:
    meta: Dict[str, Any] = {"version": _BUILD_VERSION}
    # Deployment provenance is not infrastructure detail: a consumer must be
    # able to attest WHICH source revision answered it without an operator
    # first opting in. It is therefore reported unconditionally, while the
    # Railway/Fly deploy identifiers stay behind EXPOSE_BUILD_METADATA.
    meta.update(_source_revision())
    if os.environ.get("EXPOSE_BUILD_METADATA"):
        meta["railway_commit_sha"] = os.environ.get("RAILWAY_GIT_COMMIT_SHA", "")
        meta["railway_deploy_id"] = os.environ.get("RAILWAY_DEPLOYMENT_ID", "")
        meta["fly_alloc_id"] = os.environ.get("FLY_ALLOC_ID", "")
        meta["fly_region"] = os.environ.get("FLY_REGION", "")
    return meta


@router.get("/", response_model=RootResponse)
def read_root() -> Dict[str, Any]:
    """Root endpoint. Returns service name and current engine version. No authentication required."""
    return {"status": "ok", "service": "fufire", **_build_metadata()}


def _check_ephemeris() -> DependencyStatus:
    """Try a minimal ephemeris call to verify files are present.

    Constructs a SwissEphBackend and routes through its calc_ut() wrapper
    (FQ-ATT-01, AC-01-6 / VCHK-05) instead of calling the bare global
    `swisseph.calc_ut` directly -- this closes the one call site that
    previously bypassed both the construction-time ensure_ephemeris_files()
    guard and the calc_ut() return-flag attestation check that every other
    calculation endpoint already goes through.

    Both guards are genuinely LIVE on every single call to this function, not
    checked once and cached: `ensure_ephemeris_files()` (CONTRA-1 hardening,
    fufire-premium-verification-ci) re-validates the actual filesystem state
    on every construction rather than trusting an earlier resolution, and
    `calc_ut()`'s return-flag check reflects whatever the Swiss Ephemeris
    engine genuinely computes right now. A real `SE_EPHE_PATH` pointed at an
    empty/missing directory (an operator misconfiguration or a real files
    outage) is therefore detected on the very next `/health` poll, not masked
    by a stale success from process start.
    """
    try:
        import swisseph as swe
        backend = SwissEphBackend()
        jd = swe.julday(2000, 1, 1, 12.0)
        backend.calc_ut(jd, swe.SUN)
        return DependencyStatus(status="ok")
    except Exception as e:
        return DependencyStatus(status="unavailable", detail=str(e))


def _check_rate_limiter() -> DependencyStatus:
    """Check rate limiter storage health."""
    info = get_storage_status()
    status = info["status"]
    required = bool(info.get("required", info.get("type") == "redis"))
    if status == "ok":
        return DependencyStatus(status="ok", required=required, detail=f"type={info['type']}")
    return DependencyStatus(status=status, required=required, detail=f"type={info['type']}")


def _health_payload() -> Dict[str, Any]:
    ephemeris = _check_ephemeris()
    rate_limiter = _check_rate_limiter()
    deps = {"ephemeris": ephemeris, "rate_limiter": rate_limiter}
    overall = "degraded" if any(dep.required and dep.status != "ok" for dep in deps.values()) else "healthy"
    return {
        "status": overall,
        "engine": "FuFirE",
        "version": _ENGINE_VERSION,
        "dependencies": {k: v.model_dump() for k, v in deps.items()},
    }


@router.get("/health", response_model=HealthResponse)
def health_check() -> Dict[str, Any]:
    """Liveness check. Returns engine status and per-dependency health (ephemeris). No authentication required. Use `/ready` for load-balancer probes."""
    return _health_payload()


@router.get("/ready", response_model=HealthResponse)
def readiness_check() -> Dict[str, Any] | JSONResponse:
    """Readiness endpoint for load balancers and orchestration."""
    payload = _health_payload()
    if payload["status"] != "healthy":
        return JSONResponse(status_code=503, content=payload)
    return payload


@router.get("/build", response_model=BuildResponse)
def build_info() -> Dict[str, Any]:
    """Build metadata. Returns the engine version, the immutable source revision of the running build as supplied by the deployment platform (`source_revision`, a 40-hex git object id, with its provider, kind and status), and — when `EXPOSE_BUILD_METADATA=1` — the Railway/Fly.io deploy identifiers. No authentication required."""
    return _build_metadata()


@router.get("/api", response_model=ApiResponse)
def api_endpoint(
    datum: str = Query(..., description="Datum im Format YYYY-MM-DD"),
    zeit: str = Query(..., description="Zeit im Format HH:MM[:SS]"),
    ort: Optional[str] = Query(None, description="Ort als 'lat,lon'"),
    tz: str = Query("Europe/Berlin", description="Timezone name"),
    lon: float = Query(13.4050, description="Longitude in degrees"),
    lat: float = Query(52.52, description="Latitude in degrees"),
    ambiguousTime: Literal["earlier", "later"] = Query("earlier"),
    nonexistentTime: Literal["error", "shift_forward"] = Query("error"),
) -> Dict[str, Any]:
    """Sun sign lookup. Returns the Western zodiac sign (German) for a given date, time, and location. Legacy convenience endpoint."""
    from datetime import timezone as tz_mod
    try:
        if ort:
            if "," in ort:
                parts = [p.strip() for p in ort.split(",", maxsplit=1)]
                if len(parts) == 2:
                    lat = float(parts[0])
                    lon = float(parts[1])
            else:
                raise ValueError("Ort muss als 'lat,lon' angegeben werden, wenn gesetzt.")

        dt, _ = resolve_local_iso(
            f"{datum}T{zeit}", tz,
            ambiguous=ambiguousTime, nonexistent=nonexistentTime,
        )
        dt_utc = dt.astimezone(tz_mod.utc)
        chart = compute_western_chart(dt_utc, lat, lon)
        sun = chart.get("bodies", {}).get("Sun")
        if not sun or "zodiac_sign" not in sun:
            raise ValueError("Sonnenposition konnte nicht berechnet werden.")
        sign_index = int(sun["zodiac_sign"])
        sign_name = ZODIAC_SIGNS_DE[sign_index]
        return {"sonne": sign_name, "input": {"datum": datum, "zeit": zeit, "ort": ort, "tz": tz, "lat": lat, "lon": lon}}
    except BaziEngineError:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Internal calculation error")


@router.get("/info/wuxing-mapping", response_model=WuxingMappingResponse)
def get_wuxing_mapping() -> Dict[str, Any]:
    """Wu-Xing planet mapping. Returns the canonical mapping of Western planets to Chinese Five Elements (Wu-Xing) used by the fusion engine. No authentication required."""
    return {
        "mapping": PLANET_TO_WUXING,
        "order": WUXING_ORDER,
        "description": {
            "PLANET_TO_WUXING": "Western planet to Chinese element mapping",
            "WUXING_ORDER": "Wu Xing cycle order: Holz -> Feuer -> Erde -> Metall -> Wasser",
        },
    }
