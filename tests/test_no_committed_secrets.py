"""Regression guard: no live secret material in git-tracked files.

Why this exists
---------------
A real, active ``ff_enterprise_<40-hex>`` API key was committed in plaintext to
``docs/plans/2026-04-06-superglue-proxy-endpoints.md`` and shipped in the PUBLIC
``DYAI2025/FUFIRE_API_lunar`` repository. It stayed valid — and unlimited, being
an enterprise-tier key — until it was rotated on 2026-07-25.

This test fails the build if a credential-shaped literal reappears in a tracked
file. It scans ``git ls-files`` (what actually ships to the remote), not the
working tree, so untracked scratch files and ``.env`` never trigger it.

Patterns are deliberately tuned to match *minted* secrets and not the many
placeholder literals the test-suite uses (``ff_pro_testkey123``,
``ff_free_deadbeef``, …): a minted FuFirE key is ``secrets.token_hex(16)`` →
32 lowercase hex chars, so the threshold is pure-hex ``{32,}``. Adding a new
fake key to a test is therefore safe as long as it is not 32+ hex characters.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# (name, compiled pattern). Each must match minted credentials only — never a
# structural placeholder like "ff_<tier>_<secret>" or "sk_live_...".
SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # FuFirE API key: ff_<tier>_<token_hex(16)>. 32+ pure-hex chars = minted.
    ("fufire_api_key", re.compile(r"ff_(?:free|starter|pro|enterprise)_[0-9a-f]{32,}")),
    # GitHub personal access tokens.
    ("github_token", re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,}")),
    # ElevenLabs / Stripe-style secret keys.
    ("sk_secret_key", re.compile(r"\bsk_(?:live_)?[a-zA-Z0-9]{32,}")),
    # Brevo (Sendinblue) SMTP/API keys.
    ("brevo_key", re.compile(r"xsmtpsib-[a-f0-9]{40,}")),
    # Google / Gemini API keys.
    ("google_api_key", re.compile(r"AIzaSy[A-Za-z0-9_-]{30,}")),
    # Supabase / generic HS256 JWTs (service-role keys).
    ("jwt", re.compile(r"eyJhbGciOiJIUzI1NiIs[A-Za-z0-9._-]{40,}")),
]

# Files exempt from scanning: this test itself carries the patterns.
ALLOWLIST = {"tests/test_no_committed_secrets.py"}


def _tracked_files() -> list[str]:
    """Paths git actually ships. Empty list (→ skip) outside a git checkout."""
    try:
        out = subprocess.run(
            ["git", "ls-files"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return [line for line in out.splitlines() if line]


def test_no_secret_literals_in_tracked_files() -> None:
    """Every git-tracked file is free of minted-credential literals."""
    tracked = _tracked_files()
    if not tracked:
        pytest.skip("not a git checkout — nothing to scan")

    findings: list[str] = []
    for rel in tracked:
        if rel in ALLOWLIST:
            continue
        path = REPO_ROOT / rel
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except (OSError, IsADirectoryError):
            continue  # submodule pointer, symlink, deleted-but-staged, …
        for name, pattern in SECRET_PATTERNS:
            match = pattern.search(text)
            if match is None:
                continue
            line_no = text.count("\n", 0, match.start()) + 1
            # Report the location and the KIND of secret — never the value.
            findings.append(f"{rel}:{line_no}: {name}")

    assert not findings, (
        "Credential-shaped literals found in git-tracked files. Rotate the "
        "affected secret, remove it from the file, and purge it from history:\n  "
        + "\n  ".join(findings)
    )
