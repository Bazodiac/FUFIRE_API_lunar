"""Integration tests for FastAPI endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bazi_engine.app import app

client = TestClient(app)


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_root_returns_ok(self):
        r = client.get("/")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert "service" in data

    def test_health_returns_healthy(self):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"

    def test_build_returns_version(self):
        r = client.get("/build")
        assert r.status_code == 200
        data = r.json()
        assert "version" in data

    def test_build_returns_deploy_metadata_when_exposed(self, monkeypatch):
        monkeypatch.setenv("EXPOSE_BUILD_METADATA", "1")
        r = client.get("/build")
        assert r.status_code == 200
        data = r.json()
        assert "version" in data
        assert "railway_commit_sha" in data
        assert "railway_deploy_id" in data

    def test_openapi_reports_current_build_version(self):
        r = client.get("/openapi.json")
        assert r.status_code == 200
        data = r.json()
        assert data["info"]["version"] == client.get("/build").json()["version"]


_NF_SHA = "c914d5671257b3c3ec279da76715a9338313b2e1"
_RAILWAY_SHA = "0123456789abcdef0123456789abcdef01234567"

#: Every reserved deployment variable this module reads, so a test can start
#: from a platform-free environment instead of inheriting the developer's.
_PLATFORM_VARS = (
    "NF_DEPLOYMENT_SHA",
    "NF_OBJECT_ID",
    "NF_POD_ID",
    "NF_PROJECT_ID",
    "RAILWAY_GIT_COMMIT_SHA",
    "RAILWAY_DEPLOYMENT_ID",
    "RAILWAY_SERVICE_ID",
    "RAILWAY_PROJECT_ID",
    "RAILWAY_ENVIRONMENT_ID",
    "FLY_ALLOC_ID",
    "FLY_REGION",
    "EXPOSE_BUILD_METADATA",
)


@pytest.fixture
def no_platform(monkeypatch):
    """Run with no deployment platform claiming this process."""
    for name in _PLATFORM_VARS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


class TestSourceRevisionIdentity:
    """ETBZ-34 AC 6 — `/v1/build` carries an immutable, provider-supplied
    source revision, or it carries none at all.

    The revision is read from the variable the DEPLOYMENT PLATFORM injects
    (Northflank's ``NF_DEPLOYMENT_SHA``, Railway's ``RAILWAY_GIT_COMMIT_SHA``),
    never from an application-owned value, so a consumer's attestation cannot be
    satisfied by configuration. Anything that is not a full git object id is
    refused: there is no path from "the platform told us nothing usable" to a
    revision a consumer would accept.
    """

    def test_northflank_sha_is_reported_verbatim(self, no_platform):
        no_platform.setenv("NF_DEPLOYMENT_SHA", _NF_SHA)
        no_platform.setenv("NF_POD_ID", "pod-1234")
        data = client.get("/v1/build").json()
        assert data["source_revision"] == _NF_SHA
        assert data["source_revision_provider"] == "northflank"
        assert data["source_revision_kind"] == "deployment_git_sha"
        assert data["source_revision_status"] == "available"

    def test_missing_variable_invents_no_revision(self, no_platform):
        data = client.get("/v1/build").json()
        assert data["source_revision"] is None
        assert data["source_revision_provider"] is None
        assert data["source_revision_kind"] is None
        assert data["source_revision_status"] == "unavailable"
        # The mutable version string is still there, and is still not identity.
        assert data["version"] != data["source_revision"]

    @pytest.mark.parametrize(
        "malformed",
        [
            "main",
            "abc123",
            _NF_SHA[:39],
            _NF_SHA + "a",
            _NF_SHA.upper(),
            "1.0.0-rc1-20260220",
            "sha256:" + "a" * 64,
        ],
    )
    def test_malformed_variable_is_not_acceptance_grade(self, no_platform, malformed):
        no_platform.setenv("NF_DEPLOYMENT_SHA", malformed)
        data = client.get("/v1/build").json()
        assert data["source_revision"] is None
        assert data["source_revision_status"] == "invalid"

    def test_northflank_sha_is_never_reported_under_a_railway_field(self, no_platform):
        """No alias lie: the Northflank SHA must not appear as Railway's."""
        no_platform.setenv("NF_DEPLOYMENT_SHA", _NF_SHA)
        no_platform.setenv("NF_POD_ID", "pod-1234")
        no_platform.setenv("EXPOSE_BUILD_METADATA", "1")
        data = client.get("/v1/build").json()
        assert data["source_revision"] == _NF_SHA
        assert data["railway_commit_sha"] == ""
        assert data["railway_deploy_id"] == ""
        assert data["fly_alloc_id"] == ""
        assert data["fly_region"] == ""
        for field, value in data.items():
            if field != "source_revision":
                assert value != _NF_SHA, f"{field} echoes the Northflank SHA"

    def test_railway_deployment_still_resolves(self, no_platform):
        """Existing Railway evidence is not destroyed by adding Northflank."""
        no_platform.setenv("RAILWAY_GIT_COMMIT_SHA", _RAILWAY_SHA)
        data = client.get("/v1/build").json()
        assert data["source_revision"] == _RAILWAY_SHA
        assert data["source_revision_provider"] == "railway"
        assert data["source_revision_status"] == "available"

    def test_two_platforms_resolve_by_their_own_markers(self, no_platform):
        no_platform.setenv("NF_DEPLOYMENT_SHA", _NF_SHA)
        no_platform.setenv("NF_PROJECT_ID", "fufireapi")
        no_platform.setenv("RAILWAY_GIT_COMMIT_SHA", _RAILWAY_SHA)
        data = client.get("/v1/build").json()
        assert data["source_revision"] == _NF_SHA
        assert data["source_revision_provider"] == "northflank"

        # ... and the other way round, so this is resolution, not a preference
        # for whichever provider happens to be listed first.
        no_platform.delenv("NF_PROJECT_ID")
        no_platform.setenv("RAILWAY_SERVICE_ID", "svc-1")
        data = client.get("/v1/build").json()
        assert data["source_revision"] == _RAILWAY_SHA
        assert data["source_revision_provider"] == "railway"

    @pytest.mark.parametrize("markers", [{}, {"NF_POD_ID": "p", "RAILWAY_SERVICE_ID": "s"}])
    def test_unresolvable_ambiguity_fails_closed(self, no_platform, markers):
        no_platform.setenv("NF_DEPLOYMENT_SHA", _NF_SHA)
        no_platform.setenv("RAILWAY_GIT_COMMIT_SHA", _RAILWAY_SHA)
        for name, value in markers.items():
            no_platform.setenv(name, value)
        data = client.get("/v1/build").json()
        assert data["source_revision"] is None
        assert data["source_revision_status"] == "ambiguous"

    def test_one_malformed_platform_variable_blocks_the_whole_identity(self, no_platform):
        """A misconfigured platform variable must not be masked by the other."""
        no_platform.setenv("NF_DEPLOYMENT_SHA", _NF_SHA)
        no_platform.setenv("NF_POD_ID", "pod-1234")
        no_platform.setenv("RAILWAY_GIT_COMMIT_SHA", "main")
        data = client.get("/v1/build").json()
        assert data["source_revision"] is None
        assert data["source_revision_status"] == "invalid"

    def test_legacy_and_v1_mounts_agree(self, no_platform):
        no_platform.setenv("NF_DEPLOYMENT_SHA", _NF_SHA)
        no_platform.setenv("NF_POD_ID", "pod-1234")
        assert client.get("/build").json() == client.get("/v1/build").json()

    def test_root_does_not_leak_the_source_revision_fields(self, no_platform):
        """`/` shares the helper but declares only status/service/version."""
        no_platform.setenv("NF_DEPLOYMENT_SHA", _NF_SHA)
        no_platform.setenv("NF_POD_ID", "pod-1234")
        assert set(client.get("/").json()) == {"status", "service", "version"}


class TestOpenApiContract:
    """Guardrails for fields that must stay visible in /docs."""

    @staticmethod
    def _schema_from_openapi(schema_name: str) -> dict:
        spec = client.get("/openapi.json").json()
        return spec["components"]["schemas"][schema_name]

    def test_fusion_request_has_optional_bazi_pillars(self):
        schema = self._schema_from_openapi("FusionRequest")
        assert "bazi_pillars" in schema["properties"]
        assert "bazi_pillars" not in schema.get("required", [])

    @pytest.mark.parametrize(
        ("schema_name", "required_fields"),
        [
            ("BaziRequest", {"ambiguousTime", "nonexistentTime"}),
            ("WesternRequest", {"ambiguousTime", "nonexistentTime"}),
            ("FusionRequest", {"ambiguousTime", "nonexistentTime"}),
            ("WxRequest", {"ambiguousTime", "nonexistentTime"}),
            ("TSTRequest", {"ambiguousTime", "nonexistentTime"}),
        ],
    )
    def test_dst_resolution_fields_are_present_in_all_request_schemas(self, schema_name: str, required_fields: set[str]):
        schema = self._schema_from_openapi(schema_name)
        properties = set(schema["properties"].keys())
        assert required_fields.issubset(properties)


class TestBaziEndpoint:
    """Tests for /calculate/bazi endpoint."""

    def test_basic_request(self):
        r = client.post("/calculate/bazi", json={
            "date": "2024-02-10T14:30:00",
            "tz": "Europe/Berlin",
            "lon": 13.405,
            "lat": 52.52,
        })
        assert r.status_code == 200
        data = r.json()
        assert "pillars" in data
        assert "year" in data["pillars"]
        assert "month" in data["pillars"]
        assert "day" in data["pillars"]
        assert "hour" in data["pillars"]

    def test_pillar_structure(self):
        r = client.post("/calculate/bazi", json={
            "date": "2024-02-10T14:30:00",
            "tz": "Europe/Berlin",
            "lon": 13.405,
            "lat": 52.52,
        })
        data = r.json()
        for pillar_name in ["year", "month", "day", "hour"]:
            pillar = data["pillars"][pillar_name]
            assert "stamm" in pillar
            assert "zweig" in pillar
            assert "tier" in pillar
            assert "element" in pillar

    def test_chinese_section(self):
        r = client.post("/calculate/bazi", json={
            "date": "2024-02-10T14:30:00",
            "tz": "Europe/Berlin",
            "lon": 13.405,
            "lat": 52.52,
        })
        data = r.json()
        assert "chinese" in data
        assert "year" in data["chinese"]
        assert "day_master" in data["chinese"]

    def test_dates_section(self):
        r = client.post("/calculate/bazi", json={
            "date": "2024-02-10T14:30:00",
            "tz": "Europe/Berlin",
            "lon": 13.405,
            "lat": 52.52,
        })
        data = r.json()
        assert "dates" in data
        assert "birth_local" in data["dates"]
        assert "birth_utc" in data["dates"]
        assert "lichun_local" in data["dates"]

    def test_lmt_standard(self):
        r = client.post("/calculate/bazi", json={
            "date": "2024-02-10T14:30:00",
            "tz": "Europe/Berlin",
            "lon": 13.405,
            "lat": 52.52,
            "standard": "LMT",
        })
        assert r.status_code == 200

    def test_zi_boundary(self):
        r = client.post("/calculate/bazi", json={
            "date": "2024-02-10T23:30:00",
            "tz": "Europe/Berlin",
            "lon": 13.405,
            "lat": 52.52,
            "boundary": "zi",
        })
        assert r.status_code == 200

    def test_invalid_date_returns_4xx(self):
        r = client.post("/calculate/bazi", json={
            "date": "invalid-date",
            "tz": "Europe/Berlin",
            "lon": 13.405,
            "lat": 52.52,
        })
        assert r.status_code in (400, 422)

    def test_invalid_timezone_returns_422(self):
        r = client.post("/calculate/bazi", json={
            "date": "2024-02-10T14:30:00",
            "tz": "Invalid/Timezone",
            "lon": 13.405,
            "lat": 52.52,
        })
        assert r.status_code in (400, 422)


class TestWesternEndpoint:
    """Tests for /calculate/western endpoint."""

    def test_basic_request(self):
        r = client.post("/calculate/western", json={
            "date": "2024-02-10T14:30:00",
            "tz": "Europe/Berlin",
            "lon": 13.405,
            "lat": 52.52,
        })
        assert r.status_code == 200
        data = r.json()
        assert "bodies" in data
        assert "houses" in data
        assert "angles" in data

    def test_bodies_structure(self):
        r = client.post("/calculate/western", json={
            "date": "2024-02-10T14:30:00",
            "tz": "Europe/Berlin",
            "lon": 13.405,
            "lat": 52.52,
        })
        data = r.json()
        assert "Sun" in data["bodies"]
        assert "Moon" in data["bodies"]
        sun = data["bodies"]["Sun"]
        assert "longitude" in sun
        assert "zodiac_sign" in sun

    def test_invalid_date_returns_4xx(self):
        r = client.post("/calculate/western", json={
            "date": "not-a-date",
            "tz": "Europe/Berlin",
            "lon": 13.405,
            "lat": 52.52,
        })
        assert r.status_code in (400, 422)


class TestFusionEndpoint:
    """Tests for /calculate/fusion endpoint."""

    def test_basic_request(self):
        r = client.post("/calculate/fusion", json={
            "date": "2024-02-10T14:30:00",
            "tz": "Europe/Berlin",
            "lon": 13.405,
            "lat": 52.52,
            "bazi_pillars": {
                "year": {"stem": "Jia", "branch": "Chen"},
                "month": {"stem": "Bing", "branch": "Yin"},
                "day": {"stem": "Jia", "branch": "Chen"},
                "hour": {"stem": "Xin", "branch": "Wei"},
            }
        })
        assert r.status_code == 200
        data = r.json()
        assert "wu_xing_vectors" in data
        assert "harmony_index" in data
        assert "elemental_comparison" in data
        assert "cosmic_state" in data
        assert "fusion_interpretation" in data

    def test_harmony_index_structure(self):
        r = client.post("/calculate/fusion", json={
            "date": "2024-02-10T14:30:00",
            "tz": "Europe/Berlin",
            "lon": 13.405,
            "lat": 52.52,
            "bazi_pillars": {
                "year": {"stem": "Jia", "branch": "Chen"},
                "month": {"stem": "Bing", "branch": "Yin"},
                "day": {"stem": "Jia", "branch": "Chen"},
                "hour": {"stem": "Xin", "branch": "Wei"},
            }
        })
        data = r.json()
        hi = data["harmony_index"]
        assert "harmony_index" in hi
        assert "interpretation" in hi
        assert 0 <= hi["harmony_index"] <= 1


class TestWuxingEndpoint:
    """Tests for /calculate/wuxing endpoint."""

    def test_basic_request(self):
        r = client.post("/calculate/wuxing", json={
            "date": "2024-02-10T14:30:00",
            "tz": "Europe/Berlin",
            "lon": 13.405,
            "lat": 52.52,
        })
        assert r.status_code == 200
        data = r.json()
        assert "wu_xing_vector" in data
        assert "dominant_element" in data
        assert "equation_of_time" in data
        assert "true_solar_time" in data

    def test_wuxing_vector_structure(self):
        r = client.post("/calculate/wuxing", json={
            "date": "2024-02-10T14:30:00",
            "tz": "Europe/Berlin",
            "lon": 13.405,
            "lat": 52.52,
        })
        data = r.json()
        vector = data["wu_xing_vector"]
        assert "Holz" in vector
        assert "Feuer" in vector
        assert "Erde" in vector
        assert "Metall" in vector
        assert "Wasser" in vector

    def test_dominant_element_valid(self):
        r = client.post("/calculate/wuxing", json={
            "date": "2024-02-10T14:30:00",
            "tz": "Europe/Berlin",
            "lon": 13.405,
            "lat": 52.52,
        })
        data = r.json()
        valid_elements = ["Holz", "Feuer", "Erde", "Metall", "Wasser"]
        assert data["dominant_element"] in valid_elements


class TestTstEndpoint:
    """Tests for /calculate/tst endpoint."""

    def test_basic_request(self):
        r = client.post("/calculate/tst", json={
            "date": "2024-02-10T14:30:00",
            "tz": "Europe/Berlin",
            "lon": 13.405,
        })
        assert r.status_code == 200
        data = r.json()
        assert "civil_time_hours" in data
        assert "longitude_correction_hours" in data
        assert "equation_of_time_hours" in data
        assert "true_solar_time_hours" in data
        assert "true_solar_time_formatted" in data

    def test_tst_in_valid_range(self):
        r = client.post("/calculate/tst", json={
            "date": "2024-02-10T14:30:00",
            "tz": "Europe/Berlin",
            "lon": 13.405,
        })
        data = r.json()
        assert 0 <= data["true_solar_time_hours"] < 24

    def test_formatted_time(self):
        r = client.post("/calculate/tst", json={
            "date": "2024-02-10T14:30:00",
            "tz": "Europe/Berlin",
            "lon": 13.405,
        })
        data = r.json()
        # Should be in HH:MM format
        formatted = data["true_solar_time_formatted"]
        assert ":" in formatted
        parts = formatted.split(":")
        assert len(parts) == 2
        assert 0 <= int(parts[0]) < 24
        assert 0 <= int(parts[1]) < 60


class TestApiEndpoint:
    """Tests for /api endpoint."""

    def test_basic_request(self):
        r = client.get("/api", params={
            "datum": "2024-02-10",
            "zeit": "14:30",
        })
        assert r.status_code == 200
        data = r.json()
        assert "sonne" in data

    def test_with_coordinates(self):
        r = client.get("/api", params={
            "datum": "2024-02-10",
            "zeit": "14:30",
            "lon": 13.405,
            "lat": 52.52,
        })
        assert r.status_code == 200

    def test_with_ort_lat_lon(self):
        r = client.get("/api", params={
            "datum": "2024-02-10",
            "zeit": "14:30",
            "ort": "52.52,13.405",
        })
        assert r.status_code == 200

    def test_zodiac_sign_german(self):
        r = client.get("/api", params={
            "datum": "2024-02-10",
            "zeit": "14:30",
        })
        data = r.json()
        valid_signs = [
            "Widder", "Stier", "Zwillinge", "Krebs",
            "Löwe", "Jungfrau", "Waage", "Skorpion",
            "Schütze", "Steinbock", "Wassermann", "Fische"
        ]
        assert data["sonne"] in valid_signs


class TestWuxingMappingInfo:
    """Tests for /info/wuxing-mapping endpoint."""

    def test_returns_mapping(self):
        r = client.get("/info/wuxing-mapping")
        assert r.status_code == 200
        data = r.json()
        assert "mapping" in data
        assert "order" in data
        assert "description" in data

    def test_mapping_has_planets(self):
        r = client.get("/info/wuxing-mapping")
        data = r.json()
        mapping = data["mapping"]
        assert "Sun" in mapping
        assert "Moon" in mapping
        assert "Mercury" in mapping

    def test_order_has_five_elements(self):
        r = client.get("/info/wuxing-mapping")
        data = r.json()
        order = data["order"]
        assert len(order) == 5
        assert "Holz" in order
        assert "Feuer" in order
        assert "Erde" in order
        assert "Metall" in order
        assert "Wasser" in order
