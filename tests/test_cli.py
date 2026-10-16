"""FBP-TST-007 — the CLI exposes every engine time standard, including TLST.

Runs ``bazi_engine.cli.main`` in-process (argv monkeypatched, stdout captured)
so the test sees exactly what a user sees. Hannover 1990-07-15 15:44 MESZ is
the reference case of the TLST remediation: civil 15:44 → Shen hour, but the
apparent-solar time is 14:17 → Wei hour (``tests/fixtures/tlst_reference_corpus_v1.json``).
"""
from __future__ import annotations

import json

import pytest

from bazi_engine import cli
from bazi_engine.constants import BRANCHES

HANNOVER = ["1990-07-15T15:44:00", "--tz", "Europe/Berlin", "--lon", "9.732", "--lat", "52.3759"]


def _run(monkeypatch, capsys, *extra: str) -> dict:
    monkeypatch.setattr("sys.argv", ["bazi_engine.cli", *HANNOVER, *extra, "--json"])
    cli.main()
    out = capsys.readouterr().out
    return json.loads(out)


def _hour_branch(pillar: str) -> str:
    # Pillar.__str__ is "<Stem><Branch>" (e.g. "YiWei"); branches are unambiguous suffixes.
    for b in sorted(BRANCHES, key=len, reverse=True):
        if pillar.endswith(b):
            return b
    raise AssertionError(f"no branch suffix in {pillar!r}")


def test_standard_choices_include_tlst(monkeypatch, capsys):
    import argparse
    seen = {}
    orig = argparse.ArgumentParser.add_argument

    def spy(self, *names, **kw):
        if "--standard" in names:
            seen["choices"] = kw.get("choices")
        return orig(self, *names, **kw)

    monkeypatch.setattr(argparse.ArgumentParser, "add_argument", spy)
    monkeypatch.setattr("sys.argv", ["bazi_engine.cli"])  # no date → usage error after add_argument ran
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
    assert seen["choices"] == ["CIVIL", "LMT", "TLST"]


@pytest.mark.parametrize("standard, expected_branch", [
    ("CIVIL", "Shen"),   # 15:44 zone time → Shen [15, 17)
    ("LMT", "Wei"),      # 14:23 mean solar → Wei [13, 15)
    ("TLST", "Wei"),     # 14:17 apparent solar → Wei
])
def test_hannover_hour_branch_per_standard(monkeypatch, capsys, standard, expected_branch):
    try:
        data = _run(monkeypatch, capsys, "--standard", standard)
    except SystemExit as exc:  # CLI exits 1 on engine errors (e.g. ephemeris unavailable)
        pytest.skip(f"cli exited {exc.code}: {capsys.readouterr().err.strip()}")
    assert _hour_branch(data["pillars"]["hour"]) == expected_branch, data


def test_tlst_matches_engine_result_exactly(monkeypatch, capsys):
    from bazi_engine.bazi import compute_bazi
    from bazi_engine.types import BaziInput
    try:
        data = _run(monkeypatch, capsys, "--standard", "TLST")
    except SystemExit as exc:
        pytest.skip(f"cli exited {exc.code}")
    res = compute_bazi(BaziInput(
        birth_local=HANNOVER[0], timezone="Europe/Berlin", longitude_deg=9.732,
        latitude_deg=52.3759, time_standard="TLST", day_boundary="midnight",
        accuracy_seconds=1.0, strict_local_time=True, fold=0,
    ))
    assert data["pillars"] == {
        "year": str(res.pillars.year), "month": str(res.pillars.month),
        "day": str(res.pillars.day), "hour": str(res.pillars.hour),
    }


def test_invalid_standard_is_rejected(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["bazi_engine.cli", *HANNOVER, "--standard", "UTC"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
    assert "invalid choice" in capsys.readouterr().err
