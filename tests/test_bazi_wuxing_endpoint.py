"""Tests for POST /calculate/bazi/wuxing — the canonical BaZi Wu-Xing endpoint,
and the western-planetary `basis` label added to POST /calculate/wuxing.

The BaZi Wu-Xing endpoint exposes the Four-Pillar-derived Five-Element vector
(previously only reachable embedded in /chart's `wuxing.from_bazi`). Consumers
were mistaking the planetary /calculate/wuxing for the BaZi one; these lock the
distinction: a BaZi `basis`, parity with /chart.from_bazi, and a
`western_planetary` `basis` on the planetary endpoint.
"""
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from bazi_engine.app import app
from bazi_engine.routers.bazi import BaziWuXingResponse

client = TestClient(app)

# Elke-Christina fixture (Hannover); pillars Xin Mao / Ding You / Gui Chou / Bing Chen.
BODY = {
    "date": "1951-09-10T08:20:00", "tz": "Europe/Berlin", "lon": 9.732, "lat": 52.3759,
    "standard": "CIVIL", "boundary": "midnight", "ambiguousTime": "earlier",
    "nonexistentTime": "error", "birth_time_known": True,
}
CHART_BODY = {
    "local_datetime": "1951-09-10T08:20:00", "tz_id": "Europe/Berlin",
    "geo_lon_deg": 9.732, "geo_lat_deg": 52.3759,
    "time_standard": "CIVIL", "day_boundary": "midnight", "dst_policy": "earlier",
}


def test_bazi_wuxing_shape_and_basis():
    r = client.post("/v1/calculate/bazi/wuxing", json=BODY)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["basis"] == "bazi_four_pillars"
    assert set(j["wu_xing_vector"]) == {"Holz", "Feuer", "Erde", "Metall", "Wasser"}
    # dominant is the actual argmax of the returned vector
    assert j["dominant_element"] == max(j["wu_xing_vector"], key=j["wu_xing_vector"].get)
    # ledger present and attributed to the bazi basis
    assert j["contribution_ledger"]["bazi"], "bazi contribution ledger must be non-empty"
    # the four pillars it was built from are echoed
    assert set(j["pillars"]) == {"year", "month", "day", "hour"}


def test_bazi_wuxing_equals_chart_from_bazi():
    """The new endpoint must be byte-identical to /chart's `wuxing.from_bazi`
    (it reuses the same resolve_local_iso -> BaziInput -> compute_bazi chain),
    so no consumer sees a second, diverging 'BaZi' number."""
    r = client.post("/v1/calculate/bazi/wuxing", json=BODY)
    chart = client.post("/chart", json=CHART_BODY)
    assert r.status_code == 200 and chart.status_code == 200, (r.text, chart.text)
    assert r.json()["wu_xing_vector"] == chart.json()["wuxing"]["from_bazi"]
    assert r.json()["dominant_element"] == chart.json()["wuxing"]["dominant_bazi"]


def test_planetary_wuxing_carries_western_basis():
    """The existing planetary endpoint now self-labels its provenance so a BaZi
    consumer cannot mistake it for the Four-Pillar vector."""
    r = client.post("/v1/calculate/wuxing", json={
        "date": "1951-09-10T08:20:00", "tz": "Europe/Berlin", "lon": 9.732, "lat": 52.3759,
    })
    assert r.status_code == 200, r.text
    assert r.json()["basis"] == "western_planetary"


# ─────────────────────────────────────────────────────────────────────────────
# ETBZ-35 — `basis` provenance must be OWNED BY THE PRODUCER, not the schema.
#
# `BaziWuXingResponse.basis` used to be declared as
#     Literal["bazi_four_pillars"] = Field("bazi_four_pillars", ...)
# The default made the field OPTIONAL. A handler that stopped emitting
# `"basis"` still produced a 200 whose body read `basis: "bazi_four_pillars"`,
# because the response model filled it in. Measured on this repository before
# the change: deleting the handler's `"basis"` line left every test green and
# the endpoint still claimed the provenance.
#
# That is the one failure mode the field exists to prevent. Downstream treats
# this string as PROOF OF ORIGIN — it is the only thing distinguishing this
# vector from `POST /calculate/wuxing`, whose vector comes from western
# planetary positions. A value the schema can invent is not proof of anything.
#
# So `basis` is required with no default, and the tests below pin both halves:
# the model refuses a payload that omits it, and the OpenAPI contract publishes
# it as required with a single allowed value and NO default.
# ─────────────────────────────────────────────────────────────────────────────

def _real_response_payload() -> dict:
    """A REAL producer response, not a hand-authored lookalike.

    Taking the fixture from the live endpoint means these tests measure the
    shape the handler actually emits; a hand-written dict could drift into
    proving something about itself instead.
    """
    r = client.post("/v1/calculate/bazi/wuxing", json=BODY)
    assert r.status_code == 200, r.text
    return r.json()


def test_response_model_accepts_the_real_payload_with_explicit_basis():
    payload = _real_response_payload()
    assert payload["basis"] == "bazi_four_pillars"
    assert BaziWuXingResponse(**payload).basis == "bazi_four_pillars"


def test_response_model_rejects_a_payload_without_basis():
    """The regression: the model must NOT supply the provenance itself."""
    payload = _real_response_payload()
    del payload["basis"]
    with pytest.raises(ValidationError) as excinfo:
        BaziWuXingResponse(**payload)
    assert any(err["loc"] == ("basis",) for err in excinfo.value.errors()), excinfo.value.errors()


def test_response_model_rejects_the_western_planetary_basis():
    """`POST /calculate/wuxing`'s provenance must never validate as this one."""
    payload = _real_response_payload()
    payload["basis"] = "western_planetary"
    with pytest.raises(ValidationError):
        BaziWuXingResponse(**payload)


@pytest.mark.parametrize("basis", [
    "",
    "bazi",
    "BAZI_FOUR_PILLARS",
    "bazi_four_pillars ",
    " bazi_four_pillars",
    "four_pillars",
    "fusion",
    None,
    0,
])
def test_response_model_rejects_near_miss_basis_values(basis):
    payload = _real_response_payload()
    payload["basis"] = basis
    with pytest.raises(ValidationError):
        BaziWuXingResponse(**payload)


def test_handler_still_states_the_basis_explicitly():
    """AC2 / the counterexample target.

    With `basis` required, a handler that stops emitting it can no longer be
    covered by the model: FastAPI's response validation fails and this test
    goes red. Deleting `"basis": "bazi_four_pillars"` from
    `calculate_bazi_wuxing_endpoint` is the counterexample probe for exactly
    this assertion.
    """
    r = client.post("/v1/calculate/bazi/wuxing", json=BODY)
    assert r.status_code == 200, r.text
    assert r.json()["basis"] == "bazi_four_pillars"


def _bazi_wuxing_schema() -> dict:
    app.openapi_schema = None
    spec = app.openapi()
    return spec["components"]["schemas"]["BaziWuXingResponse"]


def test_openapi_marks_basis_required():
    schema = _bazi_wuxing_schema()
    assert "basis" in schema["required"], schema["required"]


def test_openapi_restricts_basis_to_the_single_bazi_literal():
    """Asserted against MEANING, not one spelling.

    A single-value `Literal` is published as `const` by some Pydantic/FastAPI
    versions and as a one-element `enum` by others. Pinning one spelling would
    make this test fail on a toolchain bump without the contract having
    changed, so both are accepted and the VALUE is what is pinned.
    """
    basis = _bazi_wuxing_schema()["properties"]["basis"]
    allowed = set()
    if "const" in basis:
        allowed.add(basis["const"])
    if "enum" in basis:
        allowed.update(basis["enum"])
    assert allowed == {"bazi_four_pillars"}, basis


def test_openapi_publishes_no_default_for_basis():
    """A published default is the defect itself: it tells every generated
    client that an omitted `basis` may be read as `bazi_four_pillars`."""
    assert "default" not in _bazi_wuxing_schema()["properties"]["basis"]
