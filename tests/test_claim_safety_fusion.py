# tests/test_claim_safety_fusion.py
"""
FUF-147 — Claim-safety containment for raw-value harmony narration.

No production-visible fusion/daily standard path may derive positive harmony,
compatibility, or relationship prose from H_raw / raw cosine / distance before
the full calibrated card-pair model exists (FUF-55B). Raw metrics may only
appear labeled as expert diagnostics.

Boundary-proof convention (WS-A retro, 2026-07-08): HTTP-body claims are
asserted via TestClient on resp.text, not on internal objects only.
"""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from bazi_engine.app import app
from bazi_engine.fusion import compute_fusion_analysis, generate_fusion_interpretation
from bazi_engine.wuxing.analysis import interpret_harmony
from bazi_engine.wuxing.vector import WuXingVector

client = TestClient(app)

# Positive-judgment phrases that used to be emitted from raw thresholds.
# This list is the single source for all claim-safety assertions; a raw-value
# fallback reintroducing any of them must fail these tests.
FORBIDDEN_CLAIMS = [
    "Starke Resonanz",
    "starker Resonanz",
    "perfekter Harmonie",
    "Gute Harmonie",
    "ergänzen sich harmonisch",
    "unterstützen sich gegenseitig",
]


def _assert_claim_safe(text: str, context: str) -> None:
    for phrase in FORBIDDEN_CLAIMS:
        assert phrase not in text, (
            f"Forbidden raw-value judgment {phrase!r} found in {context}: {text!r}"
        )


# ── Golden fixture: high H_raw, neutral calibrated state ─────────────────────
# Synthetic dense chart (10 non-error planets, 12 BaZi Qi contributions).
# Empirically verified: h_raw = 0.7852 (would have triggered the old
# ">= 0.6 → 'starker Resonanz'" prose), h_calibrated = 0.0997 → band
# "Keine messbare Kongruenz über Baseline". Ephemeris-free by construction:
# compute_fusion_analysis() only reads pillars/bodies/ascendant.
GOLDEN_BODIES = {
    name: {"longitude": 10.0 * i, "is_retrograde": False}
    for i, name in enumerate([
        "Sun", "Moon", "Mercury", "Venus", "Mars",
        "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto",
    ])
}
GOLDEN_PILLARS = {
    "year":  {"stem": "Ren",  "branch": "Xu"},
    "month": {"stem": "Geng", "branch": "Zi"},
    "day":   {"stem": "Ren",  "branch": "You"},
    "hour":  {"stem": "Jia",  "branch": "Xu"},
}


def _golden_fusion_result() -> dict:
    return compute_fusion_analysis(
        birth_utc_dt=datetime(2024, 2, 10, 13, 30, tzinfo=timezone.utc),
        latitude=52.52,
        longitude=13.405,
        bazi_pillars=GOLDEN_PILLARS,
        western_bodies=GOLDEN_BODIES,
        ascendant=200.0,
    )


class TestGoldenFixtureHighRawNeutralCalibrated:
    """AK-2: golden fixture must not produce a positive harmony statement."""

    @pytest.fixture(scope="class")
    def fusion(self) -> dict:
        return _golden_fusion_result()

    def test_fixture_has_high_raw_value(self, fusion):
        assert fusion["calibration"]["h_raw"] >= 0.75

    def test_fixture_is_calibrated_neutral(self, fusion):
        assert fusion["calibration"]["h_calibrated"] <= 0.15
        assert fusion["calibration"]["quality"] == "ok"

    def test_fusion_interpretation_contains_no_positive_claim(self, fusion):
        _assert_claim_safe(fusion["fusion_interpretation"], "fusion_interpretation")

    def test_harmony_index_interpretation_contains_no_positive_claim(self, fusion):
        _assert_claim_safe(
            fusion["harmony_index"]["interpretation"],
            "harmony_index.interpretation",
        )

    def test_raw_value_is_labeled_as_expert_diagnostic(self, fusion):
        interp = fusion["fusion_interpretation"]
        assert "kein Nutzerurteil" in interp
        assert "Rohwert" in fusion["harmony_index"]["interpretation"]


# ── AK-1: sweep — no raw value may produce judgment prose ────────────────────
class TestRawValueSweepIsClaimSafe:
    @pytest.mark.parametrize("h", [round(x * 0.05, 2) for x in range(21)])
    def test_interpret_harmony_label_is_claim_safe(self, h):
        _assert_claim_safe(interpret_harmony(h), f"interpret_harmony({h})")

    @pytest.mark.parametrize("h", [round(x * 0.05, 2) for x in range(21)])
    def test_generate_fusion_interpretation_without_calibration_is_fail_closed(self, h):
        v = WuXingVector(1.0, 1.0, 1.0, 1.0, 1.0)
        comparison = {
            elem: {"western": 0.2, "bazi": 0.2, "difference": 0.0}
            for elem in ("Holz", "Feuer", "Erde", "Metall", "Wasser")
        }
        text = generate_fusion_interpretation(h, comparison, v, v)
        _assert_claim_safe(text, f"generate_fusion_interpretation(h={h}, no calibration)")
        assert "kein Nutzerurteil" in text


# ── AK-3: raw-value fallback guards ──────────────────────────────────────────
class TestExperienceProfileNeverFallsBackToRaw:
    def test_missing_calibration_yields_neutral_not_raw(self):
        from bazi_engine.routers.experience import _select_profile_harmony

        fusion = {
            "harmony_index": {"harmony_index": 0.94},  # high raw — must be ignored
            "calibration": {},                          # h_calibrated missing
        }
        assert _select_profile_harmony(fusion) == 0.5

    def test_calibrated_value_is_used_when_present(self):
        from bazi_engine.routers.experience import _select_profile_harmony

        fusion = {
            "harmony_index": {"harmony_index": 0.94},
            "calibration": {"h_calibrated": 0.12},
        }
        assert _select_profile_harmony(fusion) == 0.12

    def test_result_is_clamped_to_unit_interval(self):
        from bazi_engine.routers.experience import _select_profile_harmony

        assert _select_profile_harmony({"calibration": {"h_calibrated": 1.7}}) == 1.0
        assert _select_profile_harmony({"calibration": {"h_calibrated": -0.3}}) == 0.0


class TestWebhookVoiceProfileIsCalibrated:
    """AK-1/AK-3 for the ElevenLabs voice consumer (spoken to end users)."""

    def test_voice_fusion_summary_uses_calibrated_values(self):
        from bazi_engine.routers.webhooks import _voice_fusion_summary

        fusion = _golden_fusion_result()
        voice = _voice_fusion_summary(fusion)

        assert voice["harmonyIndex"] == fusion["calibration"]["h_calibrated"]
        assert voice["harmonyIndexRaw"] == fusion["calibration"]["h_raw"]
        assert voice["harmonyInterpretation"] == (
            "Keine messbare Kongruenz über Baseline"
        )
        # Spoken percent derives from the calibrated value, not the raw one.
        assert voice["harmonie"] == f"{fusion['calibration']['h_calibrated']:.0%}"
        _assert_claim_safe(voice["harmonyInterpretation"], "webhook harmonyInterpretation")


# ── HTTP boundary (WS-A convention): claims proven on resp.text ──────────────
class TestFusionEndpointBodyIsClaimSafe:
    def test_calculate_fusion_response_contains_no_positive_raw_claim(self):
        r = client.post("/calculate/fusion", json={
            "date": "2024-02-10T14:30:00",
            "tz": "Europe/Berlin",
            "lon": 13.405,
            "lat": 52.52,
            "bazi_pillars": {
                "year":  {"stem": "Jia", "branch": "Chen"},
                "month": {"stem": "Bing", "branch": "Yin"},
                "day":   {"stem": "Jia", "branch": "Chen"},
                "hour":  {"stem": "Xin", "branch": "Wei"},
            },
        })
        if r.status_code in (500, 503):
            pytest.skip(f"ephemeris unavailable: {r.status_code}")
        assert r.status_code == 200
        _assert_claim_safe(r.text, "POST /calculate/fusion response body")
        data = r.json()
        assert "Rohwert" in data["harmony_index"]["interpretation"]
        assert "kein Nutzerurteil" in data["fusion_interpretation"]
