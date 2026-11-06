"""
wuxing/constants.py — Wu-Xing domain constants (pure data, no logic).

Planet-to-Element mapping based on classical Western–Chinese
elemental correspondences and planetary rulerships.
"""
from __future__ import annotations

from typing import Dict, List, Union

# Classical Western Astrology → Chinese Five Elements (Wu Xing)
PLANET_TO_WUXING: Dict[str, Union[str, List[str]]] = {
    "Sun":          "Feuer",           # Fire  — Vitality, life force
    "Moon":         "Wasser",          # Water — Emotions, intuition
    "Mercury":      ["Erde", "Metall"],# Dual  — Earth (day chart) / Metal (night chart)
    "Venus":        "Metall",          # Metal — Beauty, value, form
    "Mars":         "Feuer",           # Fire  — Action, energy
    "Jupiter":      "Holz",            # Wood  — Growth, expansion, wisdom
    "Saturn":       "Erde",            # Earth — Structure, limits, discipline
    "Uranus":       "Holz",            # Wood  — Innovation, sudden change
    "Neptune":      "Wasser",          # Water — Dreams, spirituality
    "Pluto":        "Feuer",           # Fire  — Transformation, power
    "Chiron":       "Wasser",          # Water — Healing, wounds
    "Lilith":       "Wasser",          # Water — Dark Moon, instincts
    "NorthNode":    "Holz",            # Wood  — Future direction, growth path
    "TrueNorthNode": "Holz",
}

# Element order follows the Wu Xing generative cycle (相生)
WUXING_ORDER: List[str] = ["Holz", "Feuer", "Erde", "Metall", "Wasser"]
WUXING_INDEX: Dict[str, int] = {elem: i for i, elem in enumerate(WUXING_ORDER)}

# ── Western vector for the Fusion layer (since 2026-11-06) ────────────────────
# PLANET_TO_WUXING above assigns an element by the planet's NAME only. Because
# every chart contains the same bodies, the resulting western vector was almost
# constant (Wood led in 299 of 300 random births). The Fusion layer therefore
# translates each body through the classical element of the SIGN it occupies,
# spread over the five phases by a consensus matrix.
#
# Derivation (docs/fusion/12_west_element_mapping.md): four independent research
# runs coded the four western elements and the five phases on a shared feature
# space (hot/cold and dry/moist after Aristotle, De gen. et corr. II.2–3; vertical
# motion after De caelo IV.4 and the Shangshu Hongfan; climate of the phases
# after Suwen 5). Their season-free similarity matrices were averaged and then
# balanced (Sinkhorn: rows sum to 1, every phase receives 0.8 in total) so that
# each phase can lead on the western side. The averaging and the balancing are
# product choices, not tradition.
WESTERN_MAPPING_ID = "sign-element-consensus-v1"

# Classical elements of the twelve tropical signs, index 0 = Aries.
SIGN_ELEMENT: List[str] = ["Feuer", "Erde", "Luft", "Wasser"] * 3

# Western element → share per Wu-Xing phase. Each row sums to exactly 1.
WEST_ELEMENT_TO_WUXING: Dict[str, Dict[str, float]] = {
    "Feuer":  {"Holz": 0.452, "Feuer": 0.548, "Erde": 0.0,   "Metall": 0.0,   "Wasser": 0.0},
    "Erde":   {"Holz": 0.0,   "Feuer": 0.0,   "Erde": 0.095, "Metall": 0.699, "Wasser": 0.206},
    "Luft":   {"Holz": 0.348, "Feuer": 0.252, "Erde": 0.400, "Metall": 0.0,   "Wasser": 0.0},
    "Wasser": {"Holz": 0.0,   "Feuer": 0.0,   "Erde": 0.306, "Metall": 0.101, "Wasser": 0.593},
}
