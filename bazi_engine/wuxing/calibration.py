"""
wuxing/calibration.py — H-Kalibrierung: Kontrastverhältnis relativ zur Baseline.

PROBLEM: Der rohe Harmony Index H = cos(θ) liegt empirisch immer in [0.50, 1.0],
weil alle Vektorkomponenten ≥ 0 sind (positiver Orthant von ℝ⁵). Zwei zufällige
Charts haben einen erwarteten H-Wert von ~0.72–0.79 (abhängig von Inputdichte).
Die Deutungsschwellen 0.2 / 0.4 / 0.6 / 0.8 sind damit faktisch unerreichbar.

LÖSUNG: H_calibrated misst nicht den absoluten Winkel, sondern den *Kontrast
zur Baseline* — wie viel strukturierter ist die Übereinstimmung als bei
zufälligen Charts gleicher Dichte?

    H_calibrated = max(0, (H_raw - H_baseline) / (1.0 - H_baseline))

Wobei H_baseline = empirischer Erwartungswert für die gegebene Input-Dichte.

KALIBRIERUNGSPARAMETER (empirisch, 5000 Monte-Carlo-Trials je Zelle, Seed=42):
Reproduzierbar via: python scripts/calibrate_baselines.py --trials 5000 --seed 42

  Seit 2026-11-06 (sign-element-consensus-v1) stammt die Zelle (dense, medium)
  — die Zelle aller vollständigen Geburtshoroskope — aus ECHTEN Zufallsgeburten:
  3000 Geburten 1940–2010, zufällige Orte (|lat| ≤ 60°), BaZi in TLST, je
  5 Vertauschungen von (West_i, BaZi_j). Das synthetische Nullmodell (gleich-
  verteilte Würfe, Gewicht 1,0) bildet echte Charts nicht ab. Die übrigen
  Zellen (spärliche Eingaben) bleiben synthetisch; echte Geburten erreichen
  sie kaum (dense/sparse: 50 Paare).
  Reproduzierbar via:
    SE_EPHE_PATH=… python scripts/calibrate_baselines.py --null births --births 3000 --seed 42 --patch
  Seit 2026-11-07 (Gewichte body-tier-q0.3-v1, Aszendent als Stufe 1):
  Seeds 7 / 42 / 99 liefern 0,7958 / 0,7974 / 0,7988 (Mittel) – stabil.
  Horoskope ohne Aszendenten (unbekannte Geburtszeit) liegen im Mittel etwa
  0,015 tiefer; sigma_above ist dort um rund -0,1 verschoben.
  - n_west:  Anzahl nicht-Error-Planeten
  - n_bazi:  Gesamtzahl Qi-Beiträge aus Vier Pfeilern (Stämme + verborgene Stämme)

Das Ergebnis H_calibrated liegt in [0, 1]:
  0.0  = genau so (un)ähnlich wie zwei zufällige Charts
  1.0  = maximale Strukturkongruenz
  < 0  = weniger ähnlich als Zufall → auf 0.0 geclampt

Zusätzlich wird ein Qualitätsflag ausgegeben:
  "ok"          — normale Eingabe, Kalibrierung valide
  "sparse"      — zu wenige Planeten/Pfeiler für zuverlässiges H
  "degenerate"  — Nullvektor, H undefiniert
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .vector import WuXingVector

# ── BEGIN BASELINE_TABLE (do not edit manually — use scripts/calibrate_baselines.py) ──
_BASELINE_TABLE: dict[tuple[str, str], tuple[float, float]] = {
    ("sparse",  "sparse"):   (0.4489, 0.2672),
    ("sparse",  "medium"):   (0.5235, 0.2083),
    ("sparse",  "dense"):    (0.5464, 0.1761),
    ("medium",  "sparse"):   (0.6088, 0.2154),
    ("medium",  "medium"):   (0.6904, 0.1759),
    ("medium",  "dense"):    (0.7274, 0.1497),
    ("dense",   "sparse"):   (0.665, 0.1866),
    ("dense",   "medium"):   (0.7974, 0.1282),
    ("dense",   "dense"):    (0.7958, 0.1224),
}
# ── END BASELINE_TABLE ──

# Cells whose baseline comes from shuffled REAL births (scripts/calibrate_baselines.py
# --null births --births 3000 --seed 42) instead of the synthetic null model.
BIRTHS_CALIBRATED_CELLS: frozenset[tuple[str, str]] = frozenset({("dense", "medium")})
QualityFlag = Literal["ok", "sparse", "degenerate"]


def _n_west_bucket(n: int) -> str:
    if n <= 3:
        return "sparse"
    if n <= 8:
        return "medium"
    return "dense"


def _n_bazi_bucket(n: int) -> str:
    if n <= 8:
        return "sparse"
    if n <= 16:
        return "medium"
    return "dense"


def _count_bazi_contributions(bazi_pillars: dict) -> int:
    """Zählt die tatsächliche Gesamtzahl der Qi-Beiträge aus Vier Pfeilern.

    Jeder Stamm = 1 Beitrag, jeder Zweig = 1-3 Beiträge (verborgene Stämme)
    gemäß _BRANCH_HIDDEN. Zi/Mao/You = 1, Hai/Wu = 2, die meisten anderen = 3.
    """
    from .analysis import _BRANCH_HIDDEN
    total = 0
    for pillar_data in bazi_pillars.values():
        stem = pillar_data.get("stem", pillar_data.get("stamm", ""))
        branch = pillar_data.get("branch", pillar_data.get("zweig", ""))
        if stem:
            total += 1
        total += len(_BRANCH_HIDDEN.get(branch, []))
    return total


def _count_west_planets(western_bodies: dict) -> int:
    """Zählt Planeten ohne Error-Key."""
    return sum(1 for data in western_bodies.values() if "error" not in data)


@dataclass(frozen=True)
class CalibrationResult:
    """Kalibriertes H mit Qualitätsmeta."""
    h_raw:        float          # Originaler H-Wert aus calculate_harmony_index()
    h_calibrated: float          # Kontrastnormiertes H ∈ [0, 1]
    h_baseline:   float          # Empirische Baseline für diese Inputdichte
    h_sigma:      float          # Basislinien-Standardabweichung
    sigma_above:  float          # (H_raw - H_baseline) / H_sigma (z-Score)
    quality:      QualityFlag    # "ok" | "sparse" | "degenerate"
    n_west:       int
    n_bazi_contributions: int

    @property
    def interpretation_band(self) -> str:
        """Kalibriertes Interpretationsband basierend auf H_calibrated."""
        h = self.h_calibrated
        if self.quality == "degenerate":
            return "Undefiniert — kein Signal"
        if h >= 0.80:
            return "Starke Kongruenz"
        if h >= 0.55:
            return "Überdurchschnittliche Kongruenz"
        if h >= 0.30:
            return "Durchschnittliche Kongruenz"
        if h >= 0.10:
            return "Unterdurchschnittliche Kongruenz"
        return "Keine messbare Kongruenz über Baseline"

    @property
    def is_reliable(self) -> bool:
        return self.quality == "ok"


def calibrate_harmony(
    h_raw: float,
    western_bodies: dict,
    bazi_pillars: dict,
    western_vector: WuXingVector,
    bazi_vector: WuXingVector,
) -> CalibrationResult:
    """Kalibriert den rohen Harmony Index relativ zur empirischen Baseline.

    Args:
        h_raw:           Roher Harmony Index aus calculate_harmony_index().
        western_bodies:  Planetendaten (für Dichtezählung).
        bazi_pillars:    Vier-Pfeiler-Dict (für Dichtezählung).
        western_vector:  Rohvektor West (für Nullvektor-Erkennung).
        bazi_vector:     Rohvektor BaZi.

    Returns:
        CalibrationResult mit h_calibrated, quality, sigma_above.
    """
    n_west = _count_west_planets(western_bodies)
    n_bazi = _count_bazi_contributions(bazi_pillars)

    # Nullvektor-Check
    if western_vector.magnitude() == 0.0 or bazi_vector.magnitude() == 0.0:
        return CalibrationResult(
            h_raw=h_raw, h_calibrated=0.0, h_baseline=0.0, h_sigma=0.0,
            sigma_above=0.0, quality="degenerate",
            n_west=n_west, n_bazi_contributions=n_bazi,
        )

    # Sparse-Check
    # n_bazi threshold: < 8 = fewer than 2 full pillars worth of Qi (2 pillars × 4 avg = 8)
    quality: QualityFlag = "ok"
    if n_west < 3 or n_bazi < 8:
        quality = "sparse"

    # Baseline aus Tabelle
    wb = _n_west_bucket(n_west)
    bb = _n_bazi_bucket(n_bazi)
    h_baseline, h_sigma = _BASELINE_TABLE[(wb, bb)]

    # Kontrastnormierung
    if h_sigma < 1e-9:
        h_calibrated = 0.0
        sigma_above = 0.0
    else:
        raw_contrast = (h_raw - h_baseline) / (1.0 - h_baseline)
        h_calibrated = max(0.0, min(1.0, raw_contrast))
        sigma_above = (h_raw - h_baseline) / h_sigma

    return CalibrationResult(
        h_raw=h_raw,
        h_calibrated=round(h_calibrated, 4),
        h_baseline=round(h_baseline, 4),
        h_sigma=round(h_sigma, 4),
        sigma_above=round(sigma_above, 3),
        quality=quality,
        n_west=n_west,
        n_bazi_contributions=n_bazi,
    )
