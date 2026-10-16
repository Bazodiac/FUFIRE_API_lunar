"""bazi_engine: Astronomical BaZi (Four Pillars) calculation engine.

Version 0.2 changes vs MVP:
- DST safety checks for ambiguous/nonexistent local times (optional strict mode)
- Full 24 solar terms computation for a year window (UTC + chart-local)
- Caching hooks (can be extended) + ephemeris path injection for Swiss Ephemeris
- Skyfield adapter stub (optional dependency) + generic bisection fallback solver

Deterministic and test-first: golden vectors + invariants.
"""

from .bazi import compute_bazi
from .types import BaziInput, BaziResult, FourPillars, Pillar, SolarTerm

__version__ = "1.0.0-rc2-20261016"

__all__ = ["Pillar","FourPillars","BaziInput","BaziResult","SolarTerm","compute_bazi","__version__"]
