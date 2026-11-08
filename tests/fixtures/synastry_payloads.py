"""HTTP payloads for /v1/relationship/synastry tests (synthetic people, no real persons)."""
from __future__ import annotations

import copy
from typing import Any, Dict

SYNASTRY_PATH = "/v1/relationship/synastry"

PAIR_A: Dict[str, Any] = {"date": "1990-06-15T14:30:00", "tz": "Europe/Berlin", "lon": 13.405, "lat": 52.52}
PAIR_B: Dict[str, Any] = {"date": "1992-11-03T08:15:00", "tz": "Europe/Vienna", "lon": 16.3738, "lat": 48.2082}

VALID_SYNASTRY_REQUEST: Dict[str, Any] = {
    "person_a": {**PAIR_A, "display_label": "A."},
    "person_b": {**PAIR_B, "display_label": "B."},
    "options": {"second_person_consent_confirmed": True},
}

def request_with(**overrides: Dict[str, Any]) -> Dict[str, Any]:
    """Deep copy of the valid request with per-person/options field overrides."""
    body = copy.deepcopy(VALID_SYNASTRY_REQUEST)
    for key, fields in overrides.items():
        body[key].update(fields)
    return body

def swapped(body: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(body)
    out["person_a"], out["person_b"] = out["person_b"], out["person_a"]
    return out
