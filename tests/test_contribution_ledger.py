"""Tests: Wu-Xing contribution ledger in fusion/wuxing responses."""
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
    r = client.post("/calculate/western", json=PAYLOAD)
    return r.status_code == 200


_HAS_EPHEMERIS = _ephemeris_available()
_skip_no_ephe = pytest.mark.skipif(
    not _HAS_EPHEMERIS,
    reason="Swiss Ephemeris files not available",
)


@pytest.fixture(scope="module")
def fusion_response():
    """Cache the fusion endpoint response for the whole module."""
    r = client.post("/calculate/fusion", json=PAYLOAD)
    assert r.status_code == 200
    return r.json()


@pytest.fixture(scope="module")
def wuxing_response():
    """Cache the wuxing endpoint response for the whole module."""
    r = client.post("/calculate/wuxing", json=PAYLOAD)
    assert r.status_code == 200
    return r.json()


@_skip_no_ephe
class TestWesternContributionLedger:
    """Per-planet Wu-Xing contribution breakdown."""

    def test_fusion_has_contribution_ledger(self, fusion_response):
        assert "contribution_ledger" in fusion_response

    def test_ledger_has_western_entries(self, fusion_response):
        ledger = fusion_response["contribution_ledger"]
        assert "western" in ledger
        assert isinstance(ledger["western"], list)
        assert len(ledger["western"]) >= 5

    def test_western_entry_structure(self, fusion_response):
        entry = fusion_response["contribution_ledger"]["western"][0]
        assert "planet" in entry
        assert "element" in entry
        assert "weight" in entry
        assert "is_retrograde" in entry
        assert "category" in entry
        assert entry["element"] in ("Holz", "Feuer", "Erde", "Metall", "Wasser")
        assert entry["category"] in ("traditional", "modern_heuristic", "experimental")

    def test_mercury_entry_names_sign_element_and_chart_type(self, fusion_response):
        # sign-element-consensus-v1: the rationale names the sign element and the
        # mapping; Mercury still reports the chart-type quality of the chart.
        mercury = [e for e in fusion_response["contribution_ledger"]["western"]
                   if e["planet"] == "Mercury"]
        assert len(mercury) == 1
        assert "sign-element-consensus-v1" in mercury[0]["rationale"]
        assert mercury[0]["west_element"] in {"Feuer", "Erde", "Luft", "Wasser"}
        assert mercury[0]["chart_type_quality"] in {"exact", "assumed_day"}
        assert abs(sum(mercury[0]["distribution"].values()) - mercury[0]["weight"]) < 1e-6

    def test_retrograde_weight_is_1_3(self, fusion_response):
        for entry in fusion_response["contribution_ledger"]["western"]:
            if entry["is_retrograde"]:
                assert entry["weight"] == 1.3
            else:
                assert entry["weight"] == 1.0

    def test_wuxing_endpoint_has_contribution_ledger(self, wuxing_response):
        assert "contribution_ledger" in wuxing_response
        assert "western" in wuxing_response["contribution_ledger"]


@_skip_no_ephe
class TestBaziContributionLedger:
    """Per-pillar Wu-Xing contribution breakdown."""

    def test_ledger_has_bazi_entries(self, fusion_response):
        ledger = fusion_response["contribution_ledger"]
        assert "bazi" in ledger
        assert isinstance(ledger["bazi"], list)
        assert len(ledger["bazi"]) >= 4

    def test_bazi_entry_structure(self, fusion_response):
        entry = fusion_response["contribution_ledger"]["bazi"][0]
        assert "pillar" in entry
        assert "source" in entry
        assert "element" in entry
        assert "weight" in entry
        assert "category" in entry
        assert entry["pillar"] in ("year", "month", "day", "hour")
        assert entry["category"] == "traditional"

    def test_hidden_stems_have_qi_weights(self, fusion_response):
        hidden = [e for e in fusion_response["contribution_ledger"]["bazi"] if e["source"].startswith("hidden")]
        assert len(hidden) >= 1
        for h in hidden:
            assert h["weight"] in (1.0, 0.5, 0.3)

    def test_stem_weight_is_1(self, fusion_response):
        stems = [e for e in fusion_response["contribution_ledger"]["bazi"] if e["source"] == "stem"]
        assert len(stems) == 4
        for s in stems:
            assert s["weight"] == 1.0


@_skip_no_ephe
class TestCategoryTags:
    """Verify category assignment for contribution ledger entries."""

    TRADITIONAL_PLANETS = {"Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn"}
    MODERN_PLANETS = {"Uranus", "Neptune", "Pluto"}
    EXPERIMENTAL_BODIES = {"Chiron", "Lilith", "North Node", "South Node"}

    def test_traditional_planets_tagged_traditional(self, fusion_response):
        for entry in fusion_response["contribution_ledger"]["western"]:
            if entry["planet"] in self.TRADITIONAL_PLANETS:
                assert entry["category"] == "traditional", (
                    f"{entry['planet']} should be traditional, got {entry['category']}"
                )

    def test_modern_planets_tagged_modern_heuristic(self, fusion_response):
        for entry in fusion_response["contribution_ledger"]["western"]:
            if entry["planet"] in self.MODERN_PLANETS:
                assert entry["category"] == "modern_heuristic", (
                    f"{entry['planet']} should be modern_heuristic, got {entry['category']}"
                )

    def test_experimental_bodies_tagged_experimental(self, fusion_response):
        for entry in fusion_response["contribution_ledger"]["western"]:
            if entry["planet"] in self.EXPERIMENTAL_BODIES:
                assert entry["category"] == "experimental", (
                    f"{entry['planet']} should be experimental, got {entry['category']}"
                )

    def test_bazi_entries_all_traditional(self, fusion_response):
        for entry in fusion_response["contribution_ledger"]["bazi"]:
            assert entry["category"] == "traditional", (
                f"BaZi entry for {entry['pillar']}/{entry['source']} should be traditional"
            )
