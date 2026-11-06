"""
test_import_hierarchy.py — Enforces the module layer contract.

Layer definitions (import direction: lower → higher ONLY):
  Layer 0: constants
  Layer 1: types
  Layer 2: ephemeris, time_utils, solar_time
  Layer 3: jieqi
  Layer 4: bazi, western, fusion
  Layer 5: app, cli, bafe/*

Rules enforced:
  - No module may import from a higher layer.
  - solar_time must have zero internal imports (pure math).
  - bafe/* must not import from fusion or bazi (Layer 4 peers at same level are OK
    only via the canonical path: bafe → solar_time, not bafe → fusion).
  - Engine separation (ZWDS-P0-03): BaZi (bazi/western/fusion/impact) and ZWDS
    (zwds/*) are independent Level-4 engines that must never import each other;
    only synergy/* may import both, and synergy/* must not import Level-5
    (routers/*, app). These are DIRECTIONAL forbidden-edge rules that the numeric
    layer map cannot express (bazi and zwds are both Level 4). See FORBIDDEN_EDGES.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, List, Set, Tuple

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ENGINE_ROOT = REPO_ROOT / "bazi_engine"

# ── Layer assignments ────────────────────────────────────────────────────────
LAYERS: Dict[str, int] = {
    "constants":   0,
    "exc":         0,  # exception hierarchy — zero internal deps
    "resource_loader": 0,  # stdlib-only immutable package-resource boundary
    "provenance":  1,  # only imports __version__ — no domain deps
    "types":       1,
    "ephemeris":   2,
    "time_utils":  2,
    "solar_time":  2,
    "time_context": 2,  # FBP-01-002: pure time decomposition (CIVIL/LMT/TLST), depends only on solar_time
    "lunar_state": 2,  # canonical UTC/JD-rooted geocentric Sun/Moon state
    "jieqi":       3,
    "bazi_rules":  3,   # FBP-02-001: typed accessor over bafe.ruleset_loader
    "aspects":     4,
    "bazi":        4,
    "western":     4,
    "fusion":      4,
    # wuxing sub-modules are Level 4 peers of fusion
    "wuxing":                4,
    "wuxing.constants":      4,
    "wuxing.vector":         4,
    "wuxing.analysis":       4,
    "wuxing.zones":          4,
    "wuxing.calibration":    4,
    "wuxing.ke_cycle":       4,
    # match sub-modules are Level 4 (bazi-hehun plan §4.1): they may import
    # Levels 0-4 only — never routers/*, app, limiter or services/*.
    "match":                 4,
    "match.types":           4,
    "match.normalize":       4,
    "match.individual":      4,
    "match.ten_gods":        4,
    "match.pair":            4,
    "match.textblocks":      4,
    "match.privacy":         4,
    "match.observability":   4,
    # phases — Level 2 (pure computation, no domain imports upward)
    "phases":                2,
    "phases.jieqi_phase":    2,
    "phases.lunar_phase":    2,
    # research — Level 5 (imports from all lower levels for analysis)
    "research":              5,
    "research.dataset_generator": 5,
    "research.pattern_analysis":  5,
    "app":         5,
    "openapi_ext": 5,  # OpenAPI post-processing extracted from app.py (Task 3.21)
    "error_handlers": 5,  # global exception handlers extracted from app.py (Task 3.22)
    "auth":        5,   # API-key auth helpers (imports key_store)
    "key_store":   5,   # KeyStore backends (stdlib-only)
    "config_guard": 5,  # FUFIRE-006 startup guard — same level as auth (imports it)
    "cli":         5,
    # bafe sub-modules all live at Layer 5
    "bafe.service":         5,
    "bafe.mapping":         2,  # pure math (Stem/Branch arithmetic, TLST→hour-branch), stdlib-only
    "bafe.refdata":         5,
    "bafe.time_model":      5,
    "bafe.kernel":          5,
    "bafe.harmonics":       5,
    "bafe.canonical_json":  5,
    "bafe.errors":          5,
    "bafe.ruleset_loader":  2,  # pure data loader via the Layer-0 resource boundary
    # routers and services also live at Layer 5
    "routers.shared":       5,
    "routers.info":         5,
    "routers.bazi":         5,
    "routers.western":      5,
    "routers.fusion":       5,
    "routers.validate":     5,
    "routers.chart":        5,
    "routers.webhooks":     5,
    "routers.registry":     5,  # declarative mount table extracted from app.py (Task 3.23)
    "routers.astronomy":    5,
    "routers.bazi_tlst_v2": 5,  # FU-TLST-POLICY / INC-1: opt-in /v2 TLST BaZi + Natal
    "services.geocoding":   5,
    "services.auth":        5,
}

# Modules that are explicitly allowed to bypass the layer rule
# (e.g., re-exports for backwards compatibility must be documented here).
ALLOWED_EXCEPTIONS: Set[str] = set()

# ── Directional engine-separation edges (ZWDS-P0-03) ─────────────────────────
# The numeric LAYERS map above only forbids *upward* imports; it cannot forbid
# imports between same-layer peers. BaZi and ZWDS are BOTH Level-4 engines yet
# must stay fully separated, so those bans are expressed here as directional
# forbidden edges instead.
#
# Each entry: (source_prefix, (forbidden_import_prefix, ...)). A prefix "p"
# matches a dotted module name that is exactly "p" or a submodule "p.<sub>"
# (dot-boundary match — so "bazi" matches "bazi" and "bazi.x" but NOT the
# unrelated top-level module "bazi_rules").
FORBIDDEN_EDGES: List[Tuple[str, Tuple[str, ...]]] = [
    # ZWDS is engine-separated from BaZi: no zwds/* module may reach into the
    # BaZi engine or its Level-4 siblings.
    ("zwds", ("bazi", "western", "fusion", "impact")),
    # …and the separation is mutual: the BaZi engine must not reach into ZWDS.
    ("bazi", ("zwds",)),
    # synergy/* is the ONLY package allowed to import BOTH engines, but it is a
    # Level-4 engine package and must not import Level-5 (routers/app).
    ("synergy", ("routers", "app")),
]


def _under(name: str, prefix: str) -> bool:
    """True if dotted ``name`` is ``prefix`` itself or a submodule of it."""
    return name == prefix or name.startswith(prefix + ".")


def _collect_internal_imports(py_file: Path, package_name: str = "bazi_engine") -> List[str]:
    """Return list of bazi_engine-internal module names imported by py_file."""
    source = py_file.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(py_file))

    # Directory parts of this file relative to ENGINE_ROOT (e.g. [] for root, ["bafe"] for bafe/)
    pkg_parts = list(py_file.relative_to(ENGINE_ROOT).with_suffix("").parts[:-1])

    imported: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                # Relative import: level=1 → same package dir, level=2 → parent, etc.
                # base = pkg_parts with (level-1) trailing parts stripped
                base = pkg_parts[: max(0, len(pkg_parts) - (node.level - 1))]
                mod_parts = base + (node.module.split(".") if node.module else [])
                if mod_parts:  # skip bare "from . import x" (no module name)
                    imported.append(".".join(mod_parts))
            elif node.module and node.module.startswith(package_name + "."):
                imported.append(node.module[len(package_name) + 1 :])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(package_name + "."):
                    imported.append(alias.name[len(package_name) + 1 :])
    return imported


def _module_key(py_file: Path) -> str:
    """Convert file path to dot-notation module key used in LAYERS."""
    rel = py_file.relative_to(ENGINE_ROOT).with_suffix("")
    parts = rel.parts
    if parts[0] == "bafe":
        return "bafe." + ".".join(parts[1:])
    return ".".join(parts)


def _layer(key: str) -> int:
    return LAYERS.get(key, 5)  # unknown = treated as top layer, no rule violation possible


@pytest.mark.parametrize(
    "py_file",
    sorted(ENGINE_ROOT.rglob("*.py")),
    ids=lambda p: str(p.relative_to(ENGINE_ROOT)),
)
def test_no_upward_imports(py_file: Path):
    """Each module must only import from modules at the same or lower layer."""
    if py_file.name == "__init__.py":
        pytest.skip("__init__ files are exempt (re-export hubs)")

    key = _module_key(py_file)
    if key not in LAYERS:
        pytest.skip(f"Module '{key}' not registered in layer map — add it to LAYERS dict")

    src_layer = LAYERS[key]
    violations: List[str] = []

    for imp in _collect_internal_imports(py_file):
        imp_key = imp.split(".")[0] if "." not in imp else ".".join(imp.split(".")[:2])
        # Resolve bafe sub-modules
        if imp.startswith("bafe.") or imp == "bafe":
            imp_key = imp if imp in LAYERS else "bafe.service"
        dep_layer = _layer(imp_key)
        pair = f"{key} → {imp}"

        if dep_layer > src_layer and pair not in ALLOWED_EXCEPTIONS:
            violations.append(
                f"  Layer {src_layer} module '{key}' imports from "
                f"Layer {dep_layer} module '{imp}' (upward import!)"
            )

    if violations:
        pytest.fail(
            f"Import hierarchy violation(s) in {py_file.relative_to(ENGINE_ROOT)}:\n"
            + "\n".join(violations)
        )


def test_solar_time_has_no_internal_imports():
    """solar_time.py must be pure math — zero internal dependencies."""
    solar_time_file = ENGINE_ROOT / "solar_time.py"
    assert solar_time_file.exists(), "solar_time.py must exist"
    imports = _collect_internal_imports(solar_time_file)
    assert imports == [], (
        f"solar_time.py must have no internal imports, found: {imports}"
    )


def test_bafe_time_model_does_not_import_fusion():
    """The historical violation: bafe/time_model must NOT import fusion."""
    time_model = ENGINE_ROOT / "bafe" / "time_model.py"
    imports = _collect_internal_imports(time_model)
    fusion_imports = [i for i in imports if "fusion" in i]
    assert fusion_imports == [], (
        f"bafe/time_model.py must not import fusion. Found: {fusion_imports}"
    )


@pytest.mark.parametrize(
    "py_file",
    sorted(ENGINE_ROOT.rglob("*.py")),
    ids=lambda p: str(p.relative_to(ENGINE_ROOT)),
)
def test_engine_separation(py_file: Path):
    """Enforce the directional engine-separation edges (ZWDS-P0-03).

    Unlike ``test_no_upward_imports`` this checks ``__init__.py`` too — a
    re-export hub is exactly where a forbidden cross-engine import could sneak
    in. Rules live in ``FORBIDDEN_EDGES`` (BaZi ⇄ ZWDS mutual ban; synergy/* may
    import both engines but never Level-5 routers/app).
    """
    key = _module_key(py_file)
    imports = _collect_internal_imports(py_file)
    violations: List[str] = []

    for src_prefix, forbidden_prefixes in FORBIDDEN_EDGES:
        if not _under(key, src_prefix):
            continue
        for imp in imports:
            for forbidden in forbidden_prefixes:
                if _under(imp, forbidden):
                    violations.append(
                        f"  '{key}' (under '{src_prefix}') imports forbidden "
                        f"'{imp}' (matches ban '{forbidden}')"
                    )

    if violations:
        pytest.fail(
            f"Engine-separation violation(s) in {py_file.relative_to(ENGINE_ROOT)}:\n"
            + "\n".join(violations)
        )
