# Superglue Proxy Endpoints Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add three new API endpoints that proxy requests to Superglue.ai hooks, enabling Eve (ElevenLabs) and the frontend to fetch per-user context, daily transit, and chart data.

**Architecture:** A thin Superglue client service (`services/superglue_client.py`) wraps all httpx calls in one place. A new `routers/superglue.py` exposes the three endpoints under `/api`. Each endpoint authenticates via the existing `require_api_key` dependency (already applied globally in `app.py`).

**Tech Stack:** FastAPI, httpx (already in deps), slowapi rate limiter, pytest + respx (for mocking httpx)

---

## Background: How the existing router pattern works

- Routers define their prefix in the file: `router = APIRouter(prefix="/api", tags=[...])`
- `app.py` registers them with `app.include_router(router, dependencies=_protected)`
- `_protected = [Depends(require_api_key)]` — applies auth to all routes in the router
- Rate limits use `@limiter.limit("30/minute")` decorator on each handler

---

## Task 1: Add `respx` to dev dependencies

`respx` lets tests intercept httpx calls without a live server.

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add respx to dev deps**

In `pyproject.toml`, add `respx>=0.21.0` to `[project.optional-dependencies] dev`:

```toml
dev = [
    "pytest>=8.0",
    "httpx>=0.27.0",
    "pytest-cov>=6.0",
    "radon>=6.0",
    "respx>=0.21.0",
    "tomli>=2.0; python_version<'3.11'",
]
```

**Step 2: Install**

```bash
pip install -e ".[dev]"
```

Expected: `Successfully installed respx-...`

**Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add respx to dev deps for httpx mocking"
```

---

## Task 2: Create the Superglue client service

**Files:**
- Create: `bazi_engine/services/superglue_client.py`
- Create: `tests/test_superglue_client.py`

**Step 1: Write the failing test**

Create `tests/test_superglue_client.py`:

```python
"""Tests for Superglue hook client."""
import os
import pytest
import respx
import httpx


@pytest.fixture(autouse=True)
def set_token(monkeypatch):
    monkeypatch.setenv("SUPERGLUE_API_KEY", "test-token-123")


@respx.mock
@pytest.mark.anyio
async def test_call_hook_success():
    from bazi_engine.services.superglue_client import call_hook

    route = respx.post(
        "https://api.superglue.ai/v1/hooks/bazodiac-elevenlabs-context?token=test-token-123"
    ).mock(return_value=httpx.Response(200, json={"context": "hello"}))

    result = await call_hook("bazodiac-elevenlabs-context", {"user_id": "u_123"})

    assert result == {"context": "hello"}
    assert route.called


@respx.mock
@pytest.mark.anyio
async def test_call_hook_upstream_error():
    from bazi_engine.services.superglue_client import call_hook

    respx.post(
        "https://api.superglue.ai/v1/hooks/bazodiac-daily-transit?token=test-token-123"
    ).mock(return_value=httpx.Response(502, json={"error": "bad gateway"}))

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await call_hook("bazodiac-daily-transit", {"user_id": "u_123"})

    assert exc_info.value.response.status_code == 502


def test_call_hook_missing_token(monkeypatch):
    monkeypatch.delenv("SUPERGLUE_API_KEY", raising=False)
    from importlib import reload
    import bazi_engine.services.superglue_client as m
    reload(m)

    import asyncio
    with pytest.raises(RuntimeError, match="SUPERGLUE_API_KEY"):
        asyncio.run(m.call_hook("any-hook", {}))
```

**Step 2: Run test to confirm it fails**

```bash
pytest tests/test_superglue_client.py -v
```

Expected: `ModuleNotFoundError: No module named 'bazi_engine.services.superglue_client'`

**Step 3: Create the service**

Create `bazi_engine/services/superglue_client.py`:

```python
"""
services/superglue_client.py — HTTP client for Superglue.ai hooks.

Calls POST https://api.superglue.ai/v1/hooks/<hook>?token=<SUPERGLUE_API_KEY>
with a JSON payload and returns the parsed response.

Environment:
    SUPERGLUE_API_KEY — API token for superglue.ai (required in production)
"""
from __future__ import annotations

import os
from typing import Any, Dict

import httpx

_SUPERGLUE_BASE = "https://api.superglue.ai/v1/hooks"
_TIMEOUT = 30.0


async def call_hook(hook_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """POST to a Superglue hook and return the parsed JSON response.

    Args:
        hook_name: Hook identifier, e.g. ``bazodiac-elevenlabs-context``
        payload:   JSON body sent to the hook.

    Returns:
        Parsed JSON response dict from Superglue.

    Raises:
        RuntimeError: If SUPERGLUE_API_KEY env var is not set.
        httpx.HTTPStatusError: If Superglue returns a non-2xx status.
        httpx.TimeoutException: If the request exceeds 30 s.
    """
    token = os.environ.get("SUPERGLUE_API_KEY", "")
    if not token:
        raise RuntimeError(
            "SUPERGLUE_API_KEY environment variable is not set. "
            "Add it in Railway/Fly.io secrets."
        )

    url = f"{_SUPERGLUE_BASE}/{hook_name}?token={token}"

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()
```

**Step 4: Run tests**

```bash
pytest tests/test_superglue_client.py -v
```

Expected: all 3 tests PASS.

**Step 5: Commit**

```bash
git add bazi_engine/services/superglue_client.py tests/test_superglue_client.py
git commit -m "feat: add Superglue hook client service"
```

---

## Task 3: Create the router with three proxy endpoints

**Files:**
- Create: `bazi_engine/routers/superglue.py`
- Create: `tests/test_superglue_router.py`

**Step 1: Write the failing tests**

Create `tests/test_superglue_router.py`:

```python
"""Integration tests for /api/profile, /api/daily, /api/profile/{id}/chart endpoints."""
import os
import pytest
import respx
import httpx
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("SUPERGLUE_API_KEY", "tok_test")
    # Disable API key auth for these tests
    monkeypatch.setenv("FUFIRE_REQUIRE_API_KEYS", "false")
    monkeypatch.delenv("FUFIRE_API_KEYS", raising=False)


@pytest.fixture
def client():
    from bazi_engine.app import app
    return TestClient(app)


@respx.mock
def test_get_profile_returns_superglue_response(client):
    respx.post(
        "https://api.superglue.ai/v1/hooks/bazodiac-elevenlabs-context?token=tok_test"
    ).mock(return_value=httpx.Response(200, json={"user_id": "u_1", "context": "abc"}))

    resp = client.get("/api/profile/u_1")

    assert resp.status_code == 200
    assert resp.json()["user_id"] == "u_1"


@respx.mock
def test_get_daily_returns_superglue_response(client):
    respx.post(
        "https://api.superglue.ai/v1/hooks/bazodiac-daily-transit?token=tok_test"
    ).mock(return_value=httpx.Response(200, json={"date": "2026-04-06", "forecast": "good"}))

    resp = client.get("/api/daily/u_1")

    assert resp.status_code == 200
    assert resp.json()["date"] == "2026-04-06"


@respx.mock
def test_post_chart_returns_superglue_response(client):
    respx.post(
        "https://api.superglue.ai/v1/hooks/bazodiac-user-chart?token=tok_test"
    ).mock(return_value=httpx.Response(200, json={"chart_id": "c_99", "cached": False}))

    resp = client.post("/api/profile/u_1/chart", json={"force_recalculate": False})

    assert resp.status_code == 200
    assert resp.json()["chart_id"] == "c_99"


@respx.mock
def test_get_profile_upstream_502_returns_502(client):
    respx.post(
        "https://api.superglue.ai/v1/hooks/bazodiac-elevenlabs-context?token=tok_test"
    ).mock(return_value=httpx.Response(502))

    resp = client.get("/api/profile/u_1")

    assert resp.status_code == 502


@respx.mock
def test_get_profile_upstream_timeout_returns_504(client):
    respx.post(
        "https://api.superglue.ai/v1/hooks/bazodiac-elevenlabs-context?token=tok_test"
    ).mock(side_effect=httpx.TimeoutException("timeout"))

    resp = client.get("/api/profile/u_1")

    assert resp.status_code == 504
```

**Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_superglue_router.py -v
```

Expected: `404 Not Found` for all route tests (router not registered yet).

**Step 3: Create the router**

Create `bazi_engine/routers/superglue.py`:

```python
"""
routers/superglue.py — Superglue.ai proxy endpoints.

GET  /api/profile/{user_id}       — Fetch ElevenLabs context for user (Eve)
GET  /api/daily/{user_id}         — Fetch daily transit horoscope for user
POST /api/profile/{user_id}/chart — Trigger/refresh user chart calculation
"""
from __future__ import annotations

import logging
from typing import Any, Dict

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..limiter import limiter
from ..services.superglue_client import call_hook

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Superglue"])


class ChartRequest(BaseModel):
    force_recalculate: bool = False


def _handle_httpx_error(exc: Exception) -> HTTPException:
    if isinstance(exc, httpx.HTTPStatusError):
        return HTTPException(
            status_code=exc.response.status_code,
            detail={"error": "superglue_upstream_error", "message": str(exc)},
        )
    if isinstance(exc, httpx.TimeoutException):
        return HTTPException(
            status_code=504,
            detail={"error": "superglue_timeout", "message": "Superglue hook timed out"},
        )
    raise exc


@router.get("/profile/{user_id}")
@limiter.limit("30/minute")
async def get_profile(user_id: str, request: Request) -> Dict[str, Any]:
    """Fetch ElevenLabs context for a user via Superglue bazodiac-elevenlabs-context hook."""
    try:
        return await call_hook("bazodiac-elevenlabs-context", {"user_id": user_id})
    except (httpx.HTTPStatusError, httpx.TimeoutException) as exc:
        raise _handle_httpx_error(exc)


@router.get("/daily/{user_id}")
@limiter.limit("30/minute")
async def get_daily(user_id: str, request: Request) -> Dict[str, Any]:
    """Fetch daily transit horoscope for a user via Superglue bazodiac-daily-transit hook."""
    try:
        return await call_hook("bazodiac-daily-transit", {"user_id": user_id})
    except (httpx.HTTPStatusError, httpx.TimeoutException) as exc:
        raise _handle_httpx_error(exc)


@router.post("/profile/{user_id}/chart")
@limiter.limit("10/minute")
async def trigger_user_chart(
    user_id: str, body: ChartRequest, request: Request
) -> Dict[str, Any]:
    """Trigger or refresh chart calculation for a user via Superglue bazodiac-user-chart hook.

    Call with force_recalculate=true to bypass the Superglue cache.
    """
    try:
        return await call_hook(
            "bazodiac-user-chart",
            {"user_id": user_id, "force_recalculate": body.force_recalculate},
        )
    except (httpx.HTTPStatusError, httpx.TimeoutException) as exc:
        raise _handle_httpx_error(exc)
```

**Step 4: Run the tests**

```bash
pytest tests/test_superglue_router.py -v
```

Expected: all 5 tests PASS.

**Step 5: Commit**

```bash
git add bazi_engine/routers/superglue.py tests/test_superglue_router.py
git commit -m "feat: add Superglue proxy router (profile, daily, chart)"
```

---

## Task 4: Register the router in app.py

**Files:**
- Modify: `bazi_engine/routers/__init__.py` (if it re-exports routers)
- Modify: `bazi_engine/app.py:30` (import line) and `app.py:316` (include_router call)

**Step 1: Check what `__init__.py` exports**

```bash
grep "superglue\|from .routers" /Users/benjaminpoersch/Projects/codebase/FuFirE/bazi_engine/routers/__init__.py
```

If the `__init__.py` re-exports routers, add `superglue` there. If it's empty or doesn't exist, skip this step.

**Step 2: Add the import to app.py**

In `bazi_engine/app.py`, line 30, add `superglue` to the import:

```python
# Before:
from .routers import info, bazi, western, fusion, validate, chart, webhooks, transit, experience

# After:
from .routers import info, bazi, western, fusion, validate, chart, webhooks, transit, experience, superglue
```

**Step 3: Register the router**

In `bazi_engine/app.py`, after line 316 (`app.include_router(experience.router, dependencies=_protected)`), add:

```python
app.include_router(superglue.router, dependencies=_protected)
```

**Step 4: Run the full router test suite to confirm nothing broke**

```bash
pytest tests/test_superglue_router.py tests/test_superglue_client.py -v
```

Expected: all tests PASS.

**Step 5: Run full test suite**

```bash
pytest -q
```

Expected: no regressions. Tests that require ephemeris will skip gracefully.

**Step 6: Commit**

```bash
git add bazi_engine/app.py bazi_engine/routers/__init__.py
git commit -m "feat: register Superglue proxy router in app"
```

---

## Task 5: Add SUPERGLUE_API_KEY to production environment

**Step 1: Set the env var in Railway**

```bash
railway variables --set "SUPERGLUE_API_KEY=<your-superglue-token>"
```

Or in the Railway dashboard: **BAFE → Variables → New Variable** → `SUPERGLUE_API_KEY`.

**Step 2: Verify with a quick health check after deploy**

```bash
curl -s https://bafe-production.up.railway.app/health | jq .status
```

Expected: `"ok"` or `"healthy"`

**Step 3: Test the profile endpoint against production**

```bash
curl -s -H "X-API-Key: $FUFIRE_API_KEY" \
  "https://bafe-production.up.railway.app/api/profile/TEST_USER_ID" | jq .
```

Expected: JSON response from Superglue (or a Superglue error if `TEST_USER_ID` doesn't exist — that's fine, it means the proxy works).

---

## Task 6: Update OpenAPI spec

**Step 1: Regenerate**

```bash
python scripts/export_openapi.py
```

**Step 2: Verify no drift**

```bash
python scripts/export_openapi.py --check
```

Expected: `OK` (no diff).

**Step 3: Commit**

```bash
git add spec/openapi/openapi.json
git commit -m "docs: regenerate OpenAPI spec with Superglue proxy endpoints"
```

---

## Notes for the implementer

- `SUPERGLUE_API_KEY` is the only new secret needed. It lives exclusively in Railway/Fly.io environment — never in code or `.env` files committed to git.
- The three Superglue hooks (`bazodiac-elevenlabs-context`, `bazodiac-daily-transit`, `bazodiac-user-chart`) are external and opaque — this backend is a pure proxy.
- The `/api/profile/{user_id}` endpoint is what Eve (ElevenLabs) calls at the start of a conversation to get user context.
- The `/api/profile/{user_id}/chart` endpoint should be called on user signup or when `force_recalculate: true` is needed (e.g., after user edits birth data).
- Rate limits: profile/daily at `30/minute`, chart trigger at `10/minute` (chart is expensive on Superglue's side).
