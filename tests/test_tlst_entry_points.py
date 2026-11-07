"""2026-11-07: time standard at the product entry points, and the soulprint
sectors derived from the same consensus matrix as the western vector.

PR #79 made TLST the default at every entry point. PO decision A
(FU-TLST-POLICY/INC-1) keeps the historical CIVIL default on the public v1 and
legacy HTTP contracts (/calculate/bazi, /chart, /personalize, /impact/active,
/experience/*); TLST stays available on request where the contract has a
standard field. The CLI default (TLST since #79) is not a public v1 HTTP
contract and is not changed by decision A. The full pre-#77 pins live in
``tests/test_v1_civil_default_contract.py``.

Berlin 2016-08-15 16:00 CEST is about 14:49 apparent solar time, so the hour
pillar is Wei under TLST and Shen under civil time.
Boundary claims are asserted on real HTTP responses (WS-A convention); entry
points that expose no hour pillar are checked by spying on the engine input.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from bazi_engine import cli
from bazi_engine.app import app
from bazi_engine.provenance import WUXING_PARAMETER_SET
from bazi_engine.services.soulprint import _PHASE_SECTOR_SHARE, compute_soulprint
from bazi_engine.wuxing.constants import SIGN_ELEMENT, WEST_ELEMENT_TO_WUXING, WUXING_ORDER

client = TestClient(app)
LOCAL = "2016-08-15T16:00:00"
CHART = {"local_datetime": LOCAL, "tz_id": "Europe/Berlin", "geo_lon_deg": 13.405, "geo_lat_deg": 52.52}


def _bazi_hour(**extra):
    r = client.post("/v1/calculate/bazi", json={"date": LOCAL, "tz": "Europe/Berlin", "lat": 52.52, "lon": 13.405, **extra})
    assert r.status_code == 200, r.text
    return r.json()["pillars"]["hour"]["zweig"]


def test_reference_birth_changes_hour_pillar():
    assert _bazi_hour() == "Shen"  # v1 default CIVIL (decision A)
    assert _bazi_hour(standard="CIVIL") == "Shen"
    assert _bazi_hour(standard="TLST") == "Wei"


def test_chart_defaults_to_civil():
    default = client.post("/chart", json=CHART)
    civil = client.post("/chart", json={**CHART, "time_standard": "CIVIL"})
    tlst = client.post("/chart", json={**CHART, "time_standard": "TLST"})
    assert default.status_code == civil.status_code == tlst.status_code == 200, default.text
    assert default.json()["bazi"]["pillars"]["hour"]["branch"] == "Shen"
    assert civil.json()["bazi"]["pillars"]["hour"]["branch"] == "Shen"
    assert tlst.json()["bazi"]["pillars"]["hour"]["branch"] == "Wei"


def test_personalize_uses_civil():
    r = client.post("/personalize", json={"birth_datetime": LOCAL, "lat": 52.52, "lon": 13.405,
                                          "tz": "Europe/Berlin", "birth_time_known": True, "locale": "en"})
    assert r.status_code == 200, r.text
    body = json.dumps(r.json())
    assert '"time_standard_used": "CIVIL"' in body
    assert '"time_standard_used": "TLST"' not in body


@pytest.mark.parametrize("module", ["bazi_engine.routers.impact", "bazi_engine.routers.experience"])
def test_internal_bazi_calls_use_civil(monkeypatch, module):
    import importlib

    from bazi_engine.bazi import compute_bazi

    seen = []

    def spy(inp):
        seen.append(inp.time_standard)
        return compute_bazi(inp)

    mod = importlib.import_module(module)
    monkeypatch.setattr(mod, "compute_bazi", spy)
    if module.endswith("impact"):
        client.post("/impact/active", json={"birth": {"date": "2016-08-15", "time": "16:00", "tz": "Europe/Berlin",
                                                      "lat": 52.52, "lon": 13.405}})
    else:
        client.post("/experience/bootstrap", json={"birth": {"date": "2016-08-15", "time": "16:00:00",
                                                             "tz": "Europe/Berlin", "lat": 52.52, "lon": 13.405}})
    assert seen and set(seen) == {"CIVIL"}, seen


def test_cli_defaults_to_tlst(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["bazi_engine.cli", LOCAL, "--tz", "Europe/Berlin",
                                     "--lon", "13.405", "--lat", "52.52", "--json"])
    try:
        cli.main()
    except SystemExit as exc:  # engine errors exit 1 (e.g. ephemeris unavailable)
        pytest.skip(f"cli exited {exc.code}")
    assert json.loads(capsys.readouterr().out)["pillars"]["hour"].endswith("Wei")


def test_soulprint_sectors_are_the_transposed_consensus_matrix():
    for phase in WUXING_ORDER:
        shares = _PHASE_SECTOR_SHARE[phase]
        assert len(shares) == 12 and abs(sum(shares) - 1.0) < 1e-12
        column = [WEST_ELEMENT_TO_WUXING[SIGN_ELEMENT[s]][phase] for s in range(12)]
        assert shares == pytest.approx([c / sum(column) for c in column])
    # Metall is carried by earth signs above all: Taurus, Virgo, Capricorn.
    top = sorted(range(12), key=lambda s: -_PHASE_SECTOR_SHARE["Metall"][s])[:3]
    assert sorted(top) == [1, 5, 9]
    assert WUXING_PARAMETER_SET["wuxing_sector_mapping"].startswith("sign-element-consensus-v1 transposed")


def test_soulprint_phase_weight_keeps_its_total():
    only_phase = compute_soulprint(0, 0, 0, {}, {"Wasser": 1.0})
    no_phase = compute_soulprint(0, 0, 0, {}, {})
    # Sun, Moon and Ascendant (1 + 0.8 + 0.6) plus the whole phase weight 1.0.
    assert only_phase[0] == pytest.approx((2.4 + _PHASE_SECTOR_SHARE["Wasser"][0]) / 3.4)
    assert no_phase[0] == pytest.approx(1.0)
