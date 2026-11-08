"""POST /v1/relationship/synastry through the assembled app (TestClient boundary)."""
from __future__ import annotations

import copy

import pytest
from fastapi.testclient import TestClient

from bazi_engine.app import app
from tests.fixtures.synastry_charts import assert_mirrored
from tests.fixtures.synastry_payloads import SYNASTRY_PATH, VALID_SYNASTRY_REQUEST, request_with, swapped

client = TestClient(app)

def _post(body: dict) -> dict:
    resp = client.post(SYNASTRY_PATH, json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()

def test_response_shape() -> None:
    out = _post(VALID_SYNASTRY_REQUEST)
    assert set(out) == {"aspects", "house_overlays", "sign_layer", "wuxing_pair_factors", "provenance", "subjects"}
    assert out["subjects"] == {
        "person_a": {"display_label": "A.", "birth_time_known": True},
        "person_b": {"display_label": "B.", "birth_time_known": True},
    }
    assert out["provenance"]["orb_policy_id"] == "synastry-orbs-v1"
    assert out["provenance"]["ephemeris_mode"] in {"SWIEPH", "MOSEPH"}
    assert len(out["house_overlays"]["a_in_b"]) == 10
    assert len(out["sign_layer"]["pairs"]) == 36

def test_identical_requests_give_byte_identical_bodies() -> None:
    first = client.post(SYNASTRY_PATH, json=VALID_SYNASTRY_REQUEST)
    second = client.post(SYNASTRY_PATH, json=VALID_SYNASTRY_REQUEST)
    assert first.status_code == second.status_code == 200
    assert first.content == second.content

def test_swapping_persons_mirrors_the_response() -> None:
    ab = _post(VALID_SYNASTRY_REQUEST)
    ba = _post(swapped(VALID_SYNASTRY_REQUEST))
    assert_mirrored(ab, ba)
    assert ba["subjects"]["person_a"] == ab["subjects"]["person_b"]

def test_birth_time_gate_for_person_b() -> None:
    out = _post(request_with(person_b={"birth_time_known": False}))
    assert all(r["house"] is None and r["status"] == "unavailable_missing_time" for r in out["house_overlays"]["a_in_b"])
    assert all(1 <= r["house"] <= 12 and r["status"] == "ok" for r in out["house_overlays"]["b_in_a"])
    assert all(r["to_factor"] not in ("Ascendant", "MC") for r in out["aspects"])
    assert [e["factor"] for e in out["sign_layer"]["factors"]["person_b"]] == ["Sun", "Moon", "Mercury", "Venus", "Mars"]
    assert out["provenance"]["house_system_used"]["person_b"] is None
    assert any(w["code"] == "birth_time_unknown" and w["person"] == "person_b" for w in out["provenance"]["warnings"])

def test_v1_only_no_legacy_mount() -> None:
    assert client.post("/relationship/synastry", json=VALID_SYNASTRY_REQUEST).status_code == 404

@pytest.mark.parametrize("consent_options", [{}, {"second_person_consent_confirmed": False}])
def test_consent_is_required(consent_options: dict) -> None:
    body = copy.deepcopy(VALID_SYNASTRY_REQUEST)
    body["options"] = consent_options
    resp = client.post(SYNASTRY_PATH, json=body)
    assert resp.status_code == 422
    if consent_options:
        assert resp.json()["error"] == "consent_required"

def test_options_object_is_required() -> None:
    body = copy.deepcopy(VALID_SYNASTRY_REQUEST)
    del body["options"]
    assert client.post(SYNASTRY_PATH, json=body).status_code == 422

@pytest.mark.parametrize("field", ["date", "tz", "lon", "lat"])
def test_birth_fields_are_required(field: str) -> None:
    body = copy.deepcopy(VALID_SYNASTRY_REQUEST)
    del body["person_b"][field]
    assert client.post(SYNASTRY_PATH, json=body).status_code == 422

def test_unknown_person_fields_are_rejected() -> None:
    resp = client.post(SYNASTRY_PATH, json=request_with(person_a={"zodiac_mode": "sidereal_lahiri"}))
    assert resp.status_code == 422

@pytest.mark.parametrize("label, ok", [
    ("Anna", True), ("A.", True), ("Jean-Luc", True), ("Mary Ann", True), ("Zoë", True),
    ("A1", False), ("1990", False), ("anna@example.org", False), ("x" * 41, False), ("", False),
])
def test_display_label_is_first_name_or_initial(label: str, ok: bool) -> None:
    resp = client.post(SYNASTRY_PATH, json=request_with(person_a={"display_label": label}))
    assert (resp.status_code == 200) is ok, resp.text

def test_nonexistent_local_time_is_a_422() -> None:
    resp = client.post(SYNASTRY_PATH, json=request_with(person_b={"date": "2021-03-28T02:30:00", "tz": "Europe/Berlin"}))
    assert resp.status_code == 422

@pytest.mark.swieph
def test_real_ephemeris_is_attested() -> None:
    out = _post(VALID_SYNASTRY_REQUEST)
    assert out["provenance"]["ephemeris_mode"] == "SWIEPH"


def test_date_without_time_is_rejected_when_birth_time_known() -> None:
    resp = client.post(SYNASTRY_PATH, json=request_with(person_b={"date": "1992-11-03"}))
    assert resp.status_code == 422
    assert resp.json()["error"] == "validation_error"
    assert "1992-11-03" not in resp.text


def test_date_only_is_accepted_when_birth_time_unknown() -> None:
    resp = client.post(SYNASTRY_PATH, json=request_with(person_b={"date": "1992-11-03", "birth_time_known": False}))
    assert resp.status_code == 200, resp.text


def test_swapping_persons_mirrors_the_response_with_unknown_birth_time() -> None:
    body = request_with(person_b={"birth_time_known": False})
    ab = _post(body)
    ba = _post(swapped(body))
    assert ab["provenance"]["warnings"]
    assert_mirrored(ab, ba)
