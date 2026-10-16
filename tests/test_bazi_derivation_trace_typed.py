"""FBP-03-001 — derivation_trace must be a typed Pydantic model, not Dict[str, Any].

Verifies:
- BaziResponse.derivation_trace is an instance of BaziDerivationTrace
- All sub-models have the declared types
- JSON round-trip produces the expected key structure
- hour_branch_time_policy is present as an optional null field
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bazi_engine.app import app
from bazi_engine.routers.bazi import (
    BaziDerivationTrace,
    BaziResponse,
    DayAnchorEvidence,
    DayDerivationTrace,
    HourDerivationTrace,
    MonthDerivationTrace,
    ProvenanceIds,
    TimeResolutionTrace,
    YearDerivationTrace,
)

client = TestClient(app)

PAYLOAD = {
    "date": "2024-02-10T14:30:00",
    "tz": "Europe/Berlin",
    "lon": 13.405,
    "lat": 52.52,
}


def _ephemeris_available() -> bool:
    r = client.post("/calculate/bazi", json=PAYLOAD)
    return r.status_code == 200


_HAS_EPHEMERIS = _ephemeris_available()
_skip_no_ephe = pytest.mark.skipif(
    not _HAS_EPHEMERIS,
    reason="Swiss Ephemeris files not available",
)


class TestDerivationTraceModelsExist:
    """Typed models must be importable and have correct fields."""

    def test_bazi_derivation_trace_sub_models(self):
        fields = BaziDerivationTrace.model_fields
        assert set(fields) == {"year", "month", "day", "hour", "time_resolution", "provenance_ids"}

    def test_year_trace_fields(self):
        fields = YearDerivationTrace.model_fields
        assert "lichun_crossing_utc" in fields
        assert "is_before_lichun" in fields
        assert "solar_longitude_lichun" in fields

    def test_month_trace_fields(self):
        fields = MonthDerivationTrace.model_fields
        assert "jieqi_crossing_utc" in fields
        assert "solar_longitude_deg" in fields
        assert "month_branch_index" in fields

    def test_day_trace_fields(self):
        fields = DayDerivationTrace.model_fields
        for f in ("julian_day_number", "sexagenary_index", "day_offset_used",
                  "day_master_stem", "day_anchor_evidence"):
            assert f in fields

    def test_day_anchor_evidence_fields(self):
        fields = DayAnchorEvidence.model_fields
        for f in ("ruleset_id", "ruleset_version", "anchor_jdn",
                  "anchor_sex_idx", "anchor_verification"):
            assert f in fields

    def test_hour_trace_has_time_standard_fields(self):
        fields = HourDerivationTrace.model_fields
        assert "time_standard_requested" in fields
        assert "time_standard_used" in fields

    def test_provenance_ids_fields(self):
        fields = ProvenanceIds.model_fields
        for f in ("ruleset_id", "ruleset_version", "time_policy_id",
                  "day_anchor_id", "vector_model_id"):
            assert f in fields

    def test_time_resolution_trace_fields(self):
        fields = TimeResolutionTrace.model_fields
        for f in ("civil_local", "utc", "lmt", "tlst_hours",
                  "eot_minutes", "eot_source", "tlst_date_rollover",
                  "tz_offset_minutes", "effective_standard"):
            assert f in fields

    def test_hour_trace_has_lmt_used_field(self):
        """FBP-03-002: dedicated lmt_used flag distinguishes LMT from CIVIL and TLST."""
        fields = HourDerivationTrace.model_fields
        assert "lmt_used" in fields

    def test_hour_trace_has_optional_policy_field(self):
        """hour_branch_time_policy must exist and default to None (FBP-02-005 placeholder)."""
        fields = HourDerivationTrace.model_fields
        assert "hour_branch_time_policy" in fields
        info = fields["hour_branch_time_policy"]
        assert info.default is None

    def test_bazi_response_derivation_trace_type(self):
        """BaziResponse.derivation_trace must be typed as BaziDerivationTrace, not Dict."""
        import typing
        fields = BaziResponse.model_fields
        assert "derivation_trace" in fields
        annotation = fields["derivation_trace"].annotation
        # Unwrap Optional[BaziDerivationTrace]
        args = typing.get_args(annotation)
        inner = next((a for a in args if a is not type(None)), annotation)
        assert inner is BaziDerivationTrace


    def test_derivation_trace_models_reject_extra_fields(self):
        """All derivation trace models must have extra=forbid."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            DayAnchorEvidence(
                ruleset_id='x', ruleset_version='1', anchor_verification='ok',
                unexpected='bad',
            )
        with pytest.raises(ValidationError):
            YearDerivationTrace(
                lichun_crossing_utc='2024-02-04T02:00:00Z',
                is_before_lichun=False,
                solar_longitude_lichun=315.0,
                unexpected='bad',
            )
        with pytest.raises(ValidationError):
            TimeResolutionTrace(
                civil_local='2024-02-10T14:30:00+01:00',
                utc='2024-02-10T13:30:00+00:00',
                lmt='2024-02-10T14:23:37+00:53',
                tlst_hours=14.3,
                eot_minutes=-14.2,
                eot_source='meeus_1998',
                tlst_date_rollover=0,
                tz_offset_minutes=60,
                effective_standard='CIVIL',
                unexpected='bad',
            )
        with pytest.raises(ValidationError):
            ProvenanceIds(
                ruleset_id='standard_bazi_2026',
                ruleset_version='1.0.0',
                time_policy_id='civil_midnight',
                day_anchor_id='standard_bazi_2026:jdn_2451545_verified',
                vector_model_id='wuxing_v1.1.0',
                unexpected='bad',
            )

@_skip_no_ephe
class TestDerivationTraceEndpointTyped:
    """Live endpoint: trace JSON must match typed model structure."""

    def test_derivation_trace_json_keys(self):
        r = client.post("/calculate/bazi", json=PAYLOAD)
        assert r.status_code == 200
        trace = r.json()["derivation_trace"]
        assert set(trace.keys()) == {"year", "month", "day", "hour", "time_resolution", "provenance_ids"}

    def test_year_trace_types(self):
        r = client.post("/calculate/bazi", json=PAYLOAD)
        year = r.json()["derivation_trace"]["year"]
        assert isinstance(year["lichun_crossing_utc"], str)
        assert isinstance(year["is_before_lichun"], bool)
        assert isinstance(year["solar_longitude_lichun"], float)

    def test_month_trace_types(self):
        r = client.post("/calculate/bazi", json=PAYLOAD)
        month = r.json()["derivation_trace"]["month"]
        assert isinstance(month["jieqi_crossing_utc"], str)
        assert isinstance(month["solar_longitude_deg"], float)
        assert isinstance(month["month_branch_index"], int)

    def test_day_trace_types(self):
        r = client.post("/calculate/bazi", json=PAYLOAD)
        day = r.json()["derivation_trace"]["day"]
        assert isinstance(day["julian_day_number"], int)
        assert isinstance(day["sexagenary_index"], int)
        assert isinstance(day["day_offset_used"], int)
        assert isinstance(day["day_master_stem"], str)
        assert isinstance(day["day_anchor_evidence"], dict)

    def test_day_anchor_evidence_types(self):
        r = client.post("/calculate/bazi", json=PAYLOAD)
        ev = r.json()["derivation_trace"]["day"]["day_anchor_evidence"]
        assert isinstance(ev["ruleset_id"], str)
        assert isinstance(ev["ruleset_version"], str)
        assert isinstance(ev["anchor_verification"], str)
        # anchor_jdn and anchor_sex_idx are Optional[int]
        assert ev["anchor_jdn"] is None or isinstance(ev["anchor_jdn"], int)
        assert ev["anchor_sex_idx"] is None or isinstance(ev["anchor_sex_idx"], int)

    def test_hour_trace_types(self):
        r = client.post("/calculate/bazi", json=PAYLOAD)
        hour = r.json()["derivation_trace"]["hour"]
        assert isinstance(hour["local_hour"], int)
        assert isinstance(hour["branch_index"], int)
        assert isinstance(hour["true_solar_time_used"], bool)
        assert isinstance(hour["lmt_used"], bool)
        assert isinstance(hour["time_standard_requested"], str)
        assert isinstance(hour["time_standard_used"], str)

    def test_hour_branch_time_policy_present_as_null(self):
        """Optional placeholder field must appear in JSON output as null."""
        r = client.post("/calculate/bazi", json=PAYLOAD)
        hour = r.json()["derivation_trace"]["hour"]
        assert "hour_branch_time_policy" in hour
        assert hour["hour_branch_time_policy"] is None

    def test_civil_standard_flags(self):
        """CIVIL: both true_solar_time_used and lmt_used False (FBP-03-002)."""
        payload = {**PAYLOAD, "standard": "CIVIL"}
        r = client.post("/calculate/bazi", json=payload)
        hour = r.json()["derivation_trace"]["hour"]
        assert hour["true_solar_time_used"] is False
        assert hour["lmt_used"] is False
        assert hour["time_standard_used"] == "CIVIL"

    def test_lmt_standard_flags(self):
        """LMT: lmt_used True, true_solar_time_used False (FBP-03-002 / DEV-2026-001 fix)."""
        payload = {**PAYLOAD, "standard": "LMT"}
        r = client.post("/calculate/bazi", json=payload)
        hour = r.json()["derivation_trace"]["hour"]
        assert hour["true_solar_time_used"] is False
        assert hour["lmt_used"] is True
        assert hour["time_standard_used"] == "LMT"

    def test_tlst_standard_flags(self):
        """TLST: true_solar_time_used True, lmt_used False (FBP-03-002)."""
        payload = {**PAYLOAD, "standard": "TLST"}
        r = client.post("/calculate/bazi", json=payload)
        hour = r.json()["derivation_trace"]["hour"]
        assert hour["true_solar_time_used"] is True
        assert hour["lmt_used"] is False
        assert hour["time_standard_used"] == "TLST"

    def test_backward_compat_existing_keys_preserved(self):
        """All keys that existed before FBP-03-001 must still be present."""
        r = client.post("/calculate/bazi", json=PAYLOAD)
        trace = r.json()["derivation_trace"]
        assert "lichun_crossing_utc" in trace["year"]
        assert "is_before_lichun" in trace["year"]
        assert "jieqi_crossing_utc" in trace["month"]
        assert "julian_day_number" in trace["day"]
        assert "day_anchor_evidence" in trace["day"]
        assert "local_hour" in trace["hour"]
        assert "branch_index" in trace["hour"]

    def test_time_resolution_keys_present(self):
        """FBP-03-003: time_resolution block must contain all declared fields."""
        r = client.post("/calculate/bazi", json=PAYLOAD)
        tr = r.json()["derivation_trace"]["time_resolution"]
        for key in ("civil_local", "utc", "lmt", "tlst_hours",
                    "eot_minutes", "eot_source", "tlst_date_rollover",
                    "tz_offset_minutes", "effective_standard"):
            assert key in tr, f"time_resolution missing {key!r}"

    def test_time_resolution_types(self):
        r = client.post("/calculate/bazi", json=PAYLOAD)
        tr = r.json()["derivation_trace"]["time_resolution"]
        assert isinstance(tr["civil_local"], str)
        assert isinstance(tr["utc"], str)
        assert isinstance(tr["lmt"], str)
        assert isinstance(tr["tlst_hours"], float)
        assert isinstance(tr["eot_minutes"], float)
        assert tr["eot_source"] == "meeus_1998"
        assert isinstance(tr["tlst_date_rollover"], int)
        assert isinstance(tr["tz_offset_minutes"], int)
        assert isinstance(tr["effective_standard"], str)

    def test_time_resolution_effective_standard_matches_request(self):
        for std in ("CIVIL", "LMT", "TLST"):
            r = client.post("/calculate/bazi", json={**PAYLOAD, "standard": std})
            tr = r.json()["derivation_trace"]["time_resolution"]
            assert tr["effective_standard"] == std

    def test_time_resolution_utc_is_utc(self):
        """utc field must end with +00:00 or Z."""
        r = client.post("/calculate/bazi", json=PAYLOAD)
        utc_str = r.json()["derivation_trace"]["time_resolution"]["utc"]
        assert utc_str.endswith("+00:00") or utc_str.endswith("Z"), (
            f"expected UTC offset in {utc_str!r}"
        )

    def test_time_resolution_civil_vs_lmt_differ_nonzero_longitude(self):
        """At non-zero longitude civil_local and lmt must differ."""
        payload = {**PAYLOAD, "lon": 13.405}  # Berlin ≈ +53.6 min LMT offset
        r = client.post("/calculate/bazi", json=payload)
        tr = r.json()["derivation_trace"]["time_resolution"]
        assert tr["civil_local"] != tr["lmt"]

    def test_time_resolution_tlst_hours_in_range(self):
        r = client.post("/calculate/bazi", json=PAYLOAD)
        tlst = r.json()["derivation_trace"]["time_resolution"]["tlst_hours"]
        assert 0.0 <= tlst < 24.0

    def test_time_resolution_tz_offset_berlin_summer(self):
        """Berlin summer (2024-06-15) should have tz_offset_minutes=120 (CEST)."""
        payload = {"date": "2024-06-15T14:00:00", "tz": "Europe/Berlin",
                   "lon": 13.405, "lat": 52.52}
        r = client.post("/calculate/bazi", json=payload)
        tr = r.json()["derivation_trace"]["time_resolution"]
        assert tr["tz_offset_minutes"] == 120

    def test_provenance_ids_present(self):
        """FBP-03-004: provenance_ids block must contain all declared fields."""
        r = client.post("/calculate/bazi", json=PAYLOAD)
        pids = r.json()["derivation_trace"]["provenance_ids"]
        for key in ("ruleset_id", "ruleset_version", "time_policy_id",
                    "day_anchor_id", "vector_model_id"):
            assert key in pids, f"provenance_ids missing {key!r}"

    def test_provenance_ids_known_ruleset(self):
        r = client.post("/calculate/bazi", json=PAYLOAD)
        pids = r.json()["derivation_trace"]["provenance_ids"]
        assert pids["ruleset_id"] == "standard_bazi_2026"
        assert pids["ruleset_version"] == "1.0.0"

    def test_provenance_ids_time_policy_format(self):
        """time_policy_id must be '{standard}_{boundary}' lowercase."""
        for std, boundary, expected in [
            ("CIVIL", "midnight", "civil_midnight"),
            ("LMT", "zi", "lmt_zi"),
            ("TLST", "midnight", "tlst_midnight"),
        ]:
            r = client.post("/calculate/bazi",
                            json={**PAYLOAD, "standard": std, "boundary": boundary})
            pids = r.json()["derivation_trace"]["provenance_ids"]
            assert pids["time_policy_id"] == expected, (
                f"expected {expected!r} for {std}/{boundary}, got {pids['time_policy_id']!r}"
            )

    def test_provenance_ids_day_anchor_contains_jdn(self):
        r = client.post("/calculate/bazi", json=PAYLOAD)
        pids = r.json()["derivation_trace"]["provenance_ids"]
        assert "jdn_" in pids["day_anchor_id"]
        assert "standard_bazi_2026" in pids["day_anchor_id"]

    def test_provenance_ids_vector_model_format(self):
        r = client.post("/calculate/bazi", json=PAYLOAD)
        pids = r.json()["derivation_trace"]["provenance_ids"]
        assert pids["vector_model_id"].startswith("wuxing_v")

    def test_derivation_trace_json_keys_with_provenance(self):
        """provenance_ids key present in top-level trace dict."""
        r = client.post("/calculate/bazi", json=PAYLOAD)
        trace = r.json()["derivation_trace"]
        assert "provenance_ids" in trace
