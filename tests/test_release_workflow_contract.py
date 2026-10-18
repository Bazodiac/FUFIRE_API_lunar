from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = ROOT / ".github" / "workflows"
CI_PATH = WORKFLOWS_DIR / "ci.yml"
RELEASE_PLEASE_PATH = WORKFLOWS_DIR / "release-please.yml"
DEPENDABOT_PATH = ROOT / ".github" / "dependabot.yml"
# TASK-002 (master -> main normalization). ``main`` is canonical; ``master``
# stays a CI trigger only until the default branch and Railway's source
# branch are switched (docs/runbooks/default-branch-migration.md, phase C
# empties this tuple).
CANONICAL_BRANCH = "main"
TRANSITIONAL_BRANCHES: tuple[str, ...] = ("master",)
MANDATORY_JOBS = {
    "test",
    "typecheck",
    "lint",
    "complexity",
    "security",
    "docker-build",
    "distribution",
    "codegen",
    "contract-artifact",
}


def _workflow() -> dict[str, object]:
    loaded = yaml.safe_load(CI_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_atomic_release_gate_transitively_requires_every_mandatory_job() -> None:
    gate = _workflow()["jobs"]["release-gate"]

    assert gate["name"] == "release-gate"
    assert gate["if"] == "always()"
    assert set(gate["needs"]) == MANDATORY_JOBS
    assert "result != \"success\"" in gate["steps"][0]["run"]


def _triggers(workflow: dict[object, object]) -> dict[str, object]:
    # PyYAML (YAML 1.1) parses the bare key ``on`` as boolean True.
    triggers = workflow.get("on", workflow.get(True))
    assert isinstance(triggers, dict)
    return triggers


def test_ci_covers_canonical_main_and_transitional_branches() -> None:
    triggers = _triggers(_workflow())

    for event in ("push", "pull_request"):
        branches = triggers[event]["branches"]
        assert CANONICAL_BRANCH in branches
        assert set(branches) == {CANONICAL_BRANCH, *TRANSITIONAL_BRANCHES}


def test_ci_is_manually_dispatchable_as_branch_reachability_probe() -> None:
    assert "workflow_dispatch" in _triggers(_workflow())


def test_release_please_watches_only_the_canonical_branch() -> None:
    loaded = yaml.safe_load(RELEASE_PLEASE_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)

    assert _triggers(loaded)["push"]["branches"] == [CANONICAL_BRANCH]


def test_no_workflow_outside_ci_pins_a_transitional_branch() -> None:
    # Keeps the post-switch cleanup a one-line change in ci.yml.
    for path in sorted(WORKFLOWS_DIR.glob("*.yml")):
        if path == CI_PATH:
            continue
        raw = path.read_text(encoding="utf-8")
        for branch in TRANSITIONAL_BRANCHES:
            assert re.search(rf"\b{branch}\b", raw) is None, f"{path.name} pins {branch}"


def test_dependabot_follows_the_default_branch() -> None:
    config = yaml.safe_load(DEPENDABOT_PATH.read_text(encoding="utf-8"))

    for update in config["updates"]:
        assert "target-branch" not in update


def test_docker_gate_executes_non_root_ephemeris_runtime_smoke() -> None:
    docker_job = _workflow()["jobs"]["docker-build"]
    steps = docker_job["steps"]
    build_step = next(step for step in steps if step.get("uses", "").startswith("docker/build-push-action@"))
    runtime_step = next(step for step in steps if step.get("name", "").startswith("Verify non-root runtime"))

    assert build_step["with"]["load"] is True
    assert "os.getuid() == 10001" in runtime_step["run"]
    assert "path.read_bytes()" in runtime_step["run"]
    assert "hashlib.sha256(data).hexdigest()" in runtime_step["run"]


def test_dependabot_titles_follow_semantic_pr_policy() -> None:
    config = yaml.safe_load(DEPENDABOT_PATH.read_text(encoding="utf-8"))

    assert config["updates"]
    for update in config["updates"]:
        assert update["commit-message"] == {"prefix": "chore", "include": "scope"}
