"""Unknown birth time (D14): the chart is computed at local 12:00:00, visibly.

Authority: Confluence BG 62259202 "Unknown Birth Time / birth_time_known Contract"
(FUF-163..165). The supplied clock time is discarded; the response names the
assumption (``subjects.person_x.assumed_local_time`` / ``assumption_reason``)
and the ``birth_time_unknown`` warning says so.
"""
from __future__ import annotations

from datetime import timezone
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from bazi_engine.app import app
from bazi_engine.synastry.policy import unknown_time_day
from bazi_engine.synastry.signs import sign_entry
from bazi_engine.time_utils import resolve_local_iso
from bazi_engine.western import compute_western_chart
from tests.fixtures.synastry_payloads import SYNASTRY_PATH, request_with

client = TestClient(app)

BERLIN: Dict[str, Any] = {"tz": "Europe/Berlin", "lon": 13.405, "lat": 52.52}
# Found by a deterministic day-by-day search from 1990-01-01 (Europe/Berlin): the first
# date whose Moon sign at local 12:00 differs from 23:50 (Widder 28.18° → Stier 5.23°).
DAY_CHANGE_DATE = "1990-01-05"


def _moon_entry_at(local_iso: str, tz: str, lat: float, lon: float) -> Dict[str, Any]:
    dt_local, _ = resolve_local_iso(local_iso, tz)
    chart = compute_western_chart(dt_local.astimezone(timezone.utc), lat, lon)
    return sign_entry("Moon", float(chart["bodies"]["Moon"]["longitude"]))


def _moon_of(out: Dict[str, Any], person: str) -> Dict[str, Any]:
    return next(e for e in out["sign_layer"]["factors"][person] if e["factor"] == "Moon")


def _post(body: Dict[str, Any]) -> Dict[str, Any]:
    resp = client.post(SYNASTRY_PATH, json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


# ── policy helper ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("date, expected", [
    ("1990-01-05", ("1990-01-05", False)),
    ("  1990-01-05  ", ("1990-01-05", False)),
    ("1990-01-05T23:50:00", ("1990-01-05", True)),
    ("1990-01-05 07:00", ("1990-01-05", True)),
])
def test_unknown_time_day(date: str, expected: tuple) -> None:
    assert unknown_time_day(date) == expected


@pytest.mark.parametrize("date", ["15.06.1990", "1990-1-5", "", "19900105"])
def test_unknown_time_day_rejects_a_date_without_the_day_prefix(date: str) -> None:
    with pytest.raises(ValueError, match="date must start with YYYY-MM-DD"):
        unknown_time_day(date)


# ── HTTP boundary ────────────────────────────────────────────────────────────
@pytest.mark.swieph
def test_date_only_unknown_time_uses_local_noon() -> None:
    out = _post(request_with(person_b={"date": "1992-11-03", "birth_time_known": False}))
    ref = _moon_entry_at("1992-11-03T12:00:00", "Europe/Vienna", 48.2082, 16.3738)
    moon = _moon_of(out, "person_b")
    assert (moon["sign"], moon["degree"]) == (ref["sign"], ref["degree"])


@pytest.mark.swieph
def test_supplied_clock_time_is_discarded_across_a_moon_ingress() -> None:
    body = request_with(person_b={**BERLIN, "date": f"{DAY_CHANGE_DATE}T23:50:00", "birth_time_known": False})
    out = _post(body)
    noon = _moon_entry_at(f"{DAY_CHANGE_DATE}T12:00:00", BERLIN["tz"], BERLIN["lat"], BERLIN["lon"])
    late = _moon_entry_at(f"{DAY_CHANGE_DATE}T23:50:00", BERLIN["tz"], BERLIN["lat"], BERLIN["lon"])
    assert noon["sign"] != late["sign"]  # non-vacuous: the pinned date really crosses a sign
    moon = _moon_of(out, "person_b")
    assert (moon["sign"], moon["degree"]) == (noon["sign"], noon["degree"])
    assert moon["sign"] != late["sign"]


def _time_warning(out: Dict[str, Any], person: str) -> str:
    return next(w["detail"] for w in out["provenance"]["warnings"]
                if w["code"] == "birth_time_unknown" and w["person"] == person)


def test_warning_names_the_noon_assumption_and_the_discarded_time() -> None:
    resp = client.post(SYNASTRY_PATH, json=request_with(
        person_b={**BERLIN, "date": f"{DAY_CHANGE_DATE}T23:50:00", "birth_time_known": False}))
    assert resp.status_code == 200, resp.text
    detail = _time_warning(resp.json(), "person_b")
    assert detail == (
        "Birth time unknown: computed at the assumed local time 12:00:00; Ascendant, MC and houses "
        "are not used; the Moon range over the local day is in sign_layer. The supplied clock time was discarded."
    )
    assert "23:50" not in resp.text
    assert DAY_CHANGE_DATE not in detail


def test_warning_for_a_date_only_request_does_not_claim_a_discard() -> None:
    out = _post(request_with(person_b={"date": "1992-11-03", "birth_time_known": False}))
    detail = _time_warning(out, "person_b")
    assert "12:00:00" in detail
    assert "discarded" not in detail


def test_subjects_carry_the_assumption() -> None:
    out = _post(request_with(person_b={"date": "1992-11-03", "birth_time_known": False}))
    assert out["subjects"]["person_b"]["assumed_local_time"] == "12:00:00"
    assert out["subjects"]["person_b"]["assumption_reason"] == "birth_time_unknown"
    assert out["subjects"]["person_a"]["assumed_local_time"] is None
    assert out["subjects"]["person_a"]["assumption_reason"] is None


@pytest.mark.parametrize("date", ["15.06.1990", "1990-6-15T10:00:00"])
def test_malformed_date_with_unknown_time_is_a_validation_error(date: str) -> None:
    resp = client.post(SYNASTRY_PATH, json=request_with(person_b={"date": date, "birth_time_known": False}))
    assert resp.status_code == 422
    assert resp.json()["error"] == "validation_error"
    assert date not in resp.text
    assert "1990" not in resp.text
