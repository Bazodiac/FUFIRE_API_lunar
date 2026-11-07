"""2026-11-06: western Wu-Xing by sign element (sign-element-consensus-v1) and
TLST as an explicit, opt-in time standard for BaZi and Fusion.

PR #77 had made TLST the implicit default; FU-TLST-POLICY / INC-1 decision A
restores the v1 CIVIL default (tests/test_v1_civil_default_contract.py) while
``standard="TLST"`` stays available on request.

Boundary claims are asserted on real HTTP responses (WS-A convention).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bazi_engine.app import app
from bazi_engine.wuxing.analysis import calculate_wuxing_vector_from_planets
from bazi_engine.wuxing.constants import (
    SIGN_ELEMENT,
    WEST_ELEMENT_TO_WUXING,
    WESTERN_MAPPING_ID,
    WUXING_ORDER,
)

client = TestClient(app)

# 16:00 CEST in Berlin is about 14:49 true solar time: the hour pillar changes.
BIRTH = {"date": "2016-08-15T16:00:00", "tz": "Europe/Berlin", "lat": 52.52, "lon": 13.405}


def test_matrix_rows_sum_to_one_and_columns_are_balanced():
    assert WESTERN_MAPPING_ID == "sign-element-consensus-v1"
    for element, row in WEST_ELEMENT_TO_WUXING.items():
        assert set(row) == set(WUXING_ORDER), element
        assert all(v >= 0 for v in row.values()), element
        assert abs(sum(row.values()) - 1.0) < 1e-9, element
    for phase in WUXING_ORDER:
        column = sum(WEST_ELEMENT_TO_WUXING[e][phase] for e in WEST_ELEMENT_TO_WUXING)
        assert abs(column - 0.8) < 0.002, phase


def test_sign_elements_follow_the_triplicities():
    assert len(SIGN_ELEMENT) == 12
    assert [SIGN_ELEMENT[i] for i in (0, 4, 8)] == ["Feuer"] * 3     # Aries, Leo, Sagittarius
    assert [SIGN_ELEMENT[i] for i in (1, 5, 9)] == ["Erde"] * 3      # Taurus, Virgo, Capricorn
    assert [SIGN_ELEMENT[i] for i in (2, 6, 10)] == ["Luft"] * 3     # Gemini, Libra, Aquarius
    assert [SIGN_ELEMENT[i] for i in (3, 7, 11)] == ["Wasser"] * 3   # Cancer, Scorpio, Pisces


def test_same_planet_different_sign_gives_different_vector():
    """The element now follows the sign, not the planet's name."""
    in_aries = calculate_wuxing_vector_from_planets({"Saturn": {"longitude": 10.0, "is_retrograde": False}})
    in_taurus = calculate_wuxing_vector_from_planets({"Saturn": {"longitude": 40.0, "is_retrograde": False}})
    assert in_aries.to_list() != in_taurus.to_list()
    assert in_taurus.metall == pytest.approx(0.699 * 0.09)   # Saturn is tier 3
    assert in_aries.metall == 0


@pytest.mark.parametrize("path", ["/v1/calculate/bazi", "/v1/calculate/bazi/natal"])
def test_bazi_endpoints_default_to_civil_and_tlst_is_opt_in(path):
    default = client.post(path, json=BIRTH)
    tlst = client.post(path, json={**BIRTH, "standard": "TLST"})
    civil = client.post(path, json={**BIRTH, "standard": "CIVIL"})
    assert default.status_code == tlst.status_code == civil.status_code == 200, default.text
    d, t, c = default.json(), tlst.json(), civil.json()
    assert d["pillars"] == c["pillars"]
    assert t["pillars"] != c["pillars"], "this birth must change its hour pillar under TLST"


def test_fusion_defaults_to_civil_and_tlst_is_opt_in_for_auto_computed_pillars():
    default = client.post("/v1/calculate/fusion", json=BIRTH)
    civil = client.post("/v1/calculate/fusion", json={**BIRTH, "standard": "CIVIL"})
    tlst = client.post("/v1/calculate/fusion", json={**BIRTH, "standard": "TLST"})
    assert default.status_code == civil.status_code == tlst.status_code == 200, default.text
    bazi = lambda r: r.json()["wu_xing_vectors"]["bazi_pillars"]  # noqa: E731
    assert bazi(default) == bazi(civil)
    assert bazi(tlst) != bazi(civil)
    # The western side does not depend on the time standard (real UTC moment).
    west = lambda r: r.json()["wu_xing_vectors"]["western_planets"]  # noqa: E731
    assert west(default) == west(civil)


def test_fusion_ledger_names_sign_element_and_distribution():
    r = client.post("/v1/calculate/fusion", json=BIRTH)
    assert r.status_code == 200, r.text
    for entry in r.json()["contribution_ledger"]["western"]:
        assert entry["west_element"] == SIGN_ELEMENT[entry["sign_index"]]
        assert abs(sum(entry["distribution"].values()) - entry["weight"]) < 1e-6
        assert WESTERN_MAPPING_ID in entry["rationale"]
