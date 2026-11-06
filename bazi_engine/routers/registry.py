"""
registry.py — declarative router mount registry.

Single source of the dual-mount idiom (CLAUDE.md "Mount idiom"). Adding an
endpoint = one router module + ONE Mount line here.
tests/test_app_composition.py (route snapshot) and
tests/test_rate_limit_coverage.py enforce the rest.

Mount order is load-bearing (route matching and OpenAPI path ordering follow
registration order). ``mount_all`` preserves the historical app.py order:
legacy public mounts first (frozen for Bazodiac compatibility), then the /v1
versioned surface, then schema-hidden internal mounts.
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter, Depends, FastAPI

from ..auth import require_api_key
from ..features import feature_dependency, feature_enabled
from . import (
    admin,
    astronomy,
    bazi,
    bazi_tlst_v2,
    chart,
    chronometry,
    dayun,
    experience,
    fusion,
    geocode,
    impact,
    info,
    match,
    natal,
    personalize,
    superglue,
    transit,
    validate,
    webhooks,
    western,
    zwds,
)


@dataclass(frozen=True)
class Mount:
    """One router's mount configuration.

    - ``legacy_prefix``: prefix for the legacy (unversioned) mount; ``None``
      = no legacy mount. ``""`` mounts at the root (the common case).
    - ``v1_prefix``: prefix for the versioned mount; ``None`` = no /v1 mount.
    - ``v2_prefix``: prefix for the V2 mount; ``None`` = no /v2 mount.
    - ``protected``: apply ``Depends(require_api_key)``. Auth is enforced
      when FUFIRE_API_KEYS is set; dev-mode (empty env) bypasses.
    - ``include_in_schema``: ``False`` hides the mount from the public
      OpenAPI (internal surfaces such as webhooks).
    """

    router: APIRouter
    legacy_prefix: str | None = ""
    v1_prefix: str | None = "/v1"
    v2_prefix: str | None = None
    protected: bool = True
    include_in_schema: bool = True
    feature_flag: str | None = None


MOUNTS: tuple[Mount, ...] = (
    # info is public (health, root, build) — no API key required.
    Mount(info.router, protected=False),
    Mount(validate.router),
    Mount(bazi.router),
    Mount(dayun.router),
    # Natal per-pillar analysis (hidden stems, Ten Gods, month command).
    # Standard dual mount, like bazi/dayun.
    Mount(natal.router),
    Mount(western.router),
    Mount(fusion.router),
    # chart is internal — legacy mount only, not exposed under /v1/.
    Mount(chart.router, v1_prefix=None),
    Mount(transit.router),
    Mount(experience.router),
    # superglue keeps its historical "/api" prefix on the legacy surface and
    # mounts at plain "/v1" (NOT "/v1/api") on the versioned surface.
    Mount(superglue.router, legacy_prefix="/api"),
    Mount(impact.router),
    Mount(chronometry.router),
    Mount(geocode.router),
    Mount(personalize.router),
    # Admin key issuance. NOT behind require_api_key — it has its own X-Admin-Token
    # gate (see routers/admin.py) and returns 503 when issuance is not configured.
    Mount(
        admin.router,
        legacy_prefix=None,
        protected=False,
        feature_flag="key_issuance",
    ),
    # BaZi-Hehun pair analysis. DECISION-001 (docs/plans/2026-07-02-bazi-hehun.md,
    # docs/prd/bazi-hehun.prd.md): mounted at /v1 ONLY — NO legacy unversioned
    # /match/* mount. This is a deliberate deviation from the dual-mount idiom
    # (like the admin router): the endpoint is a new B2B surface, so the legacy
    # unauthenticated path must never exist (AC-001c kills audit chain D).
    Mount(match.router, legacy_prefix=None),
    # ZWDS (Zi Wei Dou Shu) core-seed engine. Mounted at /v1 ONLY (no legacy
    # unversioned twin) — a deliberate deviation from the dual-mount idiom, like
    # the match and admin routers: this is a new B2B surface, so no legacy
    # unauthenticated path is ever created. Protected by the default API key.
    Mount(zwds.router, legacy_prefix=None, feature_flag="zwds"),
    # Canonical astronomy contract. V2 only: its UTC-root and corrected phase
    # semantics must not appear under frozen V1 or a bare legacy alias.
    Mount(
        astronomy.router,
        legacy_prefix=None,
        v1_prefix=None,
        v2_prefix="/v2",
    ),
    # Opt-in True-Local-Solar-Time BaZi + Natal (FU-TLST-POLICY / INC-1).
    # V2 only: TLST-required, no location defaults, no silent DST fold choice —
    # semantics the frozen V1 / legacy routes must not inherit (their default
    # stays CIVIL). Protected by the default API key.
    Mount(
        bazi_tlst_v2.router,
        legacy_prefix=None,
        v1_prefix=None,
        v2_prefix="/v2",
    ),
    # Internal webhooks (ElevenLabs) — HMAC-verified, no API key, hidden from
    # the public OpenAPI.
    Mount(
        webhooks.router,
        legacy_prefix="/internal",
        v1_prefix=None,
        protected=False,
        include_in_schema=False,
    ),
)


def mount_all(app: FastAPI) -> None:
    """Mount every registered router on *app* in the historical order.

    1. Legacy public mounts (frozen for Bazodiac compatibility).
    2. /v1 versioned mounts (additive — for new B2B integrations).
    3. /v2 mounts (additive contracts with explicitly revised semantics).
    4. Internal mounts (hidden from the public OpenAPI).
    """
    def _include(mount: Mount, prefix: str) -> None:
        dependencies = []
        if mount.feature_flag is not None:
            dependencies.append(Depends(feature_dependency(mount.feature_flag)))
        if mount.protected:
            dependencies.append(Depends(require_api_key))
        visible = mount.include_in_schema and (
            mount.feature_flag is None or feature_enabled(mount.feature_flag)
        )
        app.include_router(
            mount.router,
            prefix=prefix,
            dependencies=dependencies or None,
            include_in_schema=visible,
        )

    # 1 — legacy public mounts
    for mount in MOUNTS:
        if mount.legacy_prefix is not None and mount.include_in_schema:
            _include(mount, mount.legacy_prefix)
    # 2 — /v1 versioned mounts
    for mount in MOUNTS:
        if mount.v1_prefix is not None:
            _include(mount, mount.v1_prefix)
    # 3 — /v2 mounts
    for mount in MOUNTS:
        if mount.v2_prefix is not None:
            _include(mount, mount.v2_prefix)
    # 4 — internal (schema-hidden) mounts
    for mount in MOUNTS:
        if mount.legacy_prefix is not None and not mount.include_in_schema:
            _include(mount, mount.legacy_prefix)
