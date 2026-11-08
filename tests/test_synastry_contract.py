"""Synastry contract: no score-like field (schema + live body) and no birth data in logs."""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, Iterator, Set

from fastapi.testclient import TestClient

from bazi_engine.app import app
from tests.fixtures.match_payloads import SENTINEL_A, SENTINEL_B
from tests.fixtures.synastry_payloads import SYNASTRY_PATH, VALID_SYNASTRY_REQUEST, request_with

client = TestClient(app)

_BANNED_KEY = re.compile(r"score|compat|percent|rating|points|ranking", re.IGNORECASE)
_LABEL_A, _LABEL_B = "Zephyrine", "Quillon"
_NONEXISTENT = {"date": "2021-03-28T02:31:00", "tz": "Europe/Berlin"}
_TOKENS = (
    SENTINEL_A["date"], SENTINEL_A["tz"], str(SENTINEL_A["lon"]), str(SENTINEL_A["lat"]),
    SENTINEL_B["date"], SENTINEL_B["tz"], str(SENTINEL_B["lon"]), str(SENTINEL_B["lat"]),
    "07:31", "22:04", _NONEXISTENT["date"], _LABEL_A, _LABEL_B,
)


def _refs(node: Any) -> Iterator[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                yield value.rsplit("/", 1)[-1]
            else:
                yield from _refs(value)
    elif isinstance(node, list):
        for value in node:
            yield from _refs(value)


def _reachable_components(openapi: Dict[str, Any]) -> Dict[str, Any]:
    components = openapi["components"]["schemas"]
    todo = list(_refs(openapi["paths"][SYNASTRY_PATH]["post"]))
    seen: Set[str] = set()
    while todo:
        name = todo.pop()
        if name not in seen:
            seen.add(name)
            todo.extend(_refs(components[name]))
    return {name: components[name] for name in seen}


def _property_names(node: Any) -> Iterator[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "properties" and isinstance(value, dict):
                yield from value.keys()
            yield from _property_names(value)
    elif isinstance(node, list):
        for value in node:
            yield from _property_names(value)


def _keys(node: Any) -> Iterator[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from _keys(value)
    elif isinstance(node, list):
        for value in node:
            yield from _keys(value)


def test_schema_graph_has_no_score_like_property() -> None:
    reachable = _reachable_components(app.openapi())
    assert {"SynastryRequest", "SynastryResponse", "SynastryAspect"} <= set(reachable)  # non-vacuous
    names = {n for schema in reachable.values() for n in _property_names(schema)}
    assert "weight" in names and "aspects" in names
    assert sorted(n for n in names if _BANNED_KEY.search(n)) == []


def test_live_response_has_no_score_like_key_and_no_percent_value() -> None:
    resp = client.post(SYNASTRY_PATH, json=VALID_SYNASTRY_REQUEST)
    assert resp.status_code == 200
    assert sorted(k for k in _keys(resp.json()) if _BANNED_KEY.search(k)) == []
    assert "%" not in resp.text


def _sentinel_request(**extra: Dict[str, Any]) -> Dict[str, Any]:
    body = request_with(
        person_a={**SENTINEL_A, "display_label": _LABEL_A},
        person_b={**SENTINEL_B, "display_label": _LABEL_B},
    )
    for key, fields in extra.items():
        body[key].update(fields)
    return body


def _log_blob(records: list) -> str:
    return "\n".join(f"{r.name} {r.getMessage()} {r.exc_text or ''}" for r in records)


def test_no_birth_data_or_labels_in_logs(caplog: Any) -> None:
    with caplog.at_level(logging.DEBUG):
        ok = client.post(SYNASTRY_PATH, json=_sentinel_request())
        gap = client.post(SYNASTRY_PATH, json=_sentinel_request(person_b=_NONEXISTENT))
        no_consent = client.post(SYNASTRY_PATH, json=_sentinel_request(options={"second_person_consent_confirmed": False}))
        bad_label = client.post(SYNASTRY_PATH, json=_sentinel_request(person_a={"display_label": _LABEL_A + "1"}))
    assert [ok.status_code, gap.status_code, no_consent.status_code, bad_label.status_code] == [200, 422, 422, 422]
    assert any(r.name == "bazi_engine.match.privacy" for r in caplog.records)  # non-vacuous: consent hash logged
    blob = _log_blob(caplog.records)
    assert [t for t in _TOKENS if t in blob] == []


def test_error_bodies_do_not_echo_birth_data_or_labels() -> None:
    for body in (
        _sentinel_request(person_b=_NONEXISTENT),
        _sentinel_request(options={"second_person_consent_confirmed": False}),
        _sentinel_request(person_a={"display_label": _LABEL_A + "1"}),
        _sentinel_request(person_a={"zodiac_mode": "sidereal_lahiri"}),
    ):
        resp = client.post(SYNASTRY_PATH, json=body)
        assert resp.status_code == 422
        assert [t for t in _TOKENS if t in resp.text] == [], resp.text


def test_nonexistent_local_time_error_code_and_no_echo() -> None:
    body = request_with(person_a={"date": "2021-03-28T02:30:00", "tz": "Europe/Berlin", "nonexistentTime": "error"})
    resp = client.post(SYNASTRY_PATH, json=body)
    assert resp.status_code == 422
    assert resp.json()["error"] == "dst_time_error"
    for token in ("2021-03-28", "02:30", "Europe/Berlin"):
        assert token not in resp.text


def test_empty_options_is_a_validation_error() -> None:
    resp = client.post(SYNASTRY_PATH, json={**VALID_SYNASTRY_REQUEST, "options": {}})
    assert resp.status_code == 422
    assert resp.json()["error"] == "validation_error"
