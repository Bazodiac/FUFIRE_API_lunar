"""Tests: Versionable parameter_set in Wu-Xing calculations."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bazi_engine.app import app

client = TestClient(app)

PAYLOAD = {
    "date": "2024-02-10T14:30:00",
    "tz": "Europe/Berlin",
    "lon": 13.405,
    "lat": 52.52,
}


def _ephemeris_available() -> bool:
    r = client.post("/calculate/fusion", json=PAYLOAD)
    return r.status_code == 200


_HAS_EPHEMERIS = _ephemeris_available()
_skip_no_ephe = pytest.mark.skipif(
    not _HAS_EPHEMERIS,
    reason="Swiss Ephemeris files not available",
)


@_skip_no_ephe
class TestParameterSet:
    def test_provenance_has_parameter_set(self):
        r = client.post("/calculate/fusion", json=PAYLOAD)
        data = r.json()
        assert "parameter_set" in data["provenance"]

    def test_parameter_set_has_version(self):
        r = client.post("/calculate/fusion", json=PAYLOAD)
        data = r.json()
        ps = data["provenance"]["parameter_set"]
        assert "version" in ps

    def test_parameter_set_has_retrograde_weight(self):
        r = client.post("/calculate/fusion", json=PAYLOAD)
        data = r.json()
        ps = data["provenance"]["parameter_set"]
        assert "retrograde_weight" in ps
        # body-tier-q0.3-v1 (2026-11-07): no extra weight for retrograde bodies.
        assert ps["retrograde_weight"] == 1.0

    def test_parameter_set_states_the_western_weights_the_engine_uses(self):
        """provenance.py (Layer 1) carries a literal copy of the wuxing constants;
        the copy must equal what the engine computes with, on the real response."""
        from bazi_engine.wuxing.constants import (
            WESTERN_BODY_TIER,
            WESTERN_EXCLUDED_BODIES,
            WESTERN_MAPPING_ID,
            WESTERN_TIER_WEIGHT,
            WESTERN_WEIGHTING_ID,
        )
        r = client.post("/calculate/fusion", json=PAYLOAD)
        ps = r.json()["provenance"]["parameter_set"]
        assert ps["western_mapping_id"] == WESTERN_MAPPING_ID
        assert ps["western_weighting_id"] == WESTERN_WEIGHTING_ID
        assert ps["western_tier_weight"] == {str(k): v for k, v in WESTERN_TIER_WEIGHT.items()}
        assert ps["western_body_tier"] == WESTERN_BODY_TIER
        assert ps["western_excluded_bodies"] == sorted(WESTERN_EXCLUDED_BODIES)
        assert ps["mercury_dual_rule"] == "none"

    def test_parameter_set_has_hidden_stem_weights(self):
        r = client.post("/calculate/fusion", json=PAYLOAD)
        data = r.json()
        ps = data["provenance"]["parameter_set"]
        assert "hidden_stem_main_qi" in ps
        assert ps["hidden_stem_main_qi"] == 1.0
        assert "hidden_stem_middle_qi" in ps
        assert ps["hidden_stem_middle_qi"] == 0.5
        assert "hidden_stem_residual_qi" in ps
        assert ps["hidden_stem_residual_qi"] == 0.3

    def test_parameter_set_in_wuxing_endpoint(self):
        r = client.post("/calculate/wuxing", json=PAYLOAD)
        data = r.json()
        assert "parameter_set" in data["provenance"]


def test_parameter_set_contains_differentiated_orbs():
    """Differentiated aspect orb model must be documented in parameter_set."""
    from bazi_engine.provenance import WUXING_PARAMETER_SET
    assert WUXING_PARAMETER_SET["aspect_orb_model"] == "differentiated_v1"

    base_orbs = WUXING_PARAMETER_SET["aspect_base_orbs"]
    assert base_orbs["Sun"] == 10.0
    assert base_orbs["Moon"] == 10.0
    assert base_orbs["Chiron"] == 3.0
    assert base_orbs["Lilith"] == 2.0

    factors = WUXING_PARAMETER_SET["aspect_factors"]
    assert factors["conjunction"] == 1.0
    assert factors["sextile"] == 0.75
    assert factors["opposition"] == 1.0


def test_parameter_set_contains_soulprint_weights():
    """Soulprint weights must be documented in parameter_set."""
    from bazi_engine.provenance import WUXING_PARAMETER_SET
    sp = WUXING_PARAMETER_SET["soulprint_weights"]
    assert sp["sun"] == 1.0
    assert sp["moon"] == 0.8
    assert sp["ascendant"] == 0.6
    assert sp["personal_planet"] == 0.4


def test_parameter_set_contains_transit_weights():
    """Transit planet weights must be documented in parameter_set."""
    from bazi_engine.provenance import WUXING_PARAMETER_SET
    tw = WUXING_PARAMETER_SET["transit_planet_weights"]
    assert tw["pluto"] == 2.0
    assert tw["neptune"] == 1.8
    assert tw["uranus"] == 1.5
