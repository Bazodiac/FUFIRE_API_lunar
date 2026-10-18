# Runbook: Default-branch normalization `master` → `main` (TASK-002)

**Plan:** `docs/plans/2026-07-21-fufire-api-lunar-release-readiness.md`, TASK-002 (REQ-A-001).
**Goal:** `main` is the default, deployed and release branch; no active consumer points at `master`.

The work is split into three phases. Only phase A is a code change; phase B needs
repository-admin and Railway access; phase C is a small follow-up PR.

| Phase | Who | What | Reversible |
|-------|-----|------|------------|
| A | PR | CI gains `workflow_dispatch`; branch wiring becomes a tested contract; this runbook | yes (revert) |
| B | Repo admin + Railway owner | switch default branch and Railway source branch in one sitting | yes (see Rollback) |
| C | PR | drop `master` from CI triggers and docs | yes (revert) |

---

## State evidenced on 2026-10-18 (before phase B)

| Fact | Value | Source |
|------|-------|--------|
| Default branch | `master` (HEAD → `refs/heads/master`) | `git ls-remote --symref origin HEAD` |
| `main` vs `master` | `main` is a strict ancestor: 0 commits ahead, 30 behind | `git rev-list --left-right --count origin/main...origin/master` |
| Open PRs | 9, all Dependabot, all based on `master` | GitHub PR list |
| Branch protection | no branch reports `protected: true` | GitHub branch list (rulesets not exported here — check in the UI) |
| CI triggers | `push`/`pull_request` on `[main, master]` | `.github/workflows/ci.yml` |
| release-please trigger | `push` on `[main]` only | `.github/workflows/release-please.yml` |
| release-please health | runs 2–5 on `main` all failed: `Input required and not supplied: token` | run 29973352302, job 89099889396 |
| CI dispatch on `main` | refused: `Workflow does not have 'workflow_dispatch' trigger` | dispatch attempt, 2026-10-18 (red pre-state for plan step 1) |
| Railway source branch | **unknown from the repo** (CLAUDE.md says Railway deploys `master`) | must be read in the Railway dashboard |

### Blocker independent of the branch switch

`RELEASE_PLEASE_TOKEN` is not provisioned. The workflow fails closed by design, so
TASK-002's acceptance "release-please runs" cannot be met by the switch alone. Provision a
fine-grained PAT or GitHub App token (contents: write, pull-requests: write on this repo) as the
Actions secret `RELEASE_PLEASE_TOKEN` before or right after phase B.

Expected first release-please result once the token exists (inference, verify on the PR):
no `vX` tag exists, so the commit range starts at `bootstrap-sha` `fe8f019`; the manifest
says `1.5.0`; there are `feat:` commits and no `!:`/`BREAKING CHANGE` markers in
`fe8f019..master` → the release PR should propose **1.6.0**, matching the fixed next
release. If it proposes anything else, do not merge it; pin with `"release-as": "1.6.0"`
in `release-please-config.json` for that one release.

---

## Phase B — switch (repo admin + Railway owner, same sitting)

Two ways exist. **Use B-rename.** B-switch is the fallback if deleting `main` is not acceptable.

| | B-rename (recommended) | B-switch |
|-|------------------------|----------|
| Mechanism | delete `main`, rename `master` → `main` | fast-forward `main`, change default to `main` |
| 9 open Dependabot PRs | retargeted to `main` by GitHub | stay on `master`; retarget by hand or close |
| Branch protection / rulesets naming `master` | updated by GitHub for explicit name rules | must be recreated for `main` |
| Web links to `master` | redirected | not redirected |
| Leftover `master` | none | must be frozen or deleted afterwards |
| Data risk | none: `main` has no commits that `master` lacks (re-check in B0) | none |

Neither way redirects git operations: clones and scripts using `master` must be updated
(GitHub shows a hint to clone owners after a rename).

### B0 — preflight (run immediately before B1)

```bash
git fetch origin master main
git merge-base --is-ancestor origin/main origin/master && echo "OK: main is an ancestor"
git rev-list --count origin/master..origin/main   # must print 0
git ls-remote --symref origin HEAD                # expect refs/heads/master
```

Also: no PR open against `main` (GitHub → Pull requests → filter `base:main`), and no
in-flight Railway deploy.

### B1 — GitHub (B-rename)

1. Settings → Branches (or Code → Branches): delete branch `main`.
   Safe only if B0 printed `0`.
2. Settings → General → Default branch → rename `master` to `main`. Read the dialog's list
   of effects and confirm.
3. Check: Code → Branches shows only `main` as default; the 9 Dependabot PRs show base `main`;
   Settings → Rules/Branches shows any rules on `main`.

### B1' — GitHub (B-switch, fallback)

1. `git push origin origin/master:refs/heads/main` (fast-forward only; it fails if not a FF).
2. Settings → General → Default branch → switch to `main`.
3. Recreate any branch rules for `main`; retarget or close the Dependabot PRs.
4. Freeze `master`: a ruleset that blocks pushes, or delete it after phase C.

### B2 — Railway (immediately after B1)

1. Railway → service → Settings → Source → Branch: set `main`. Keep auto-deploy on.
2. Note the value it had before (needed for rollback and for the evidence ledger).

If this step is late, nothing breaks: Railway keeps running the last `master` deploy and
simply does not deploy merges to `main` until the source is switched.

### B3 — verification

1. Merge the first PR into `main` (the phase-C PR is a good candidate).
2. CI: a `push` run of `CI` on `main` for that merge commit, with `release-gate` green.
3. Dispatch: Actions → CI → Run workflow → branch `main` succeeds (green post-state of plan step 1).
4. release-please: a run on `main`; green once the token exists, else it fails with the token error above.
5. Railway: a deploy for the merge commit; then `GET /build` returns that commit as
   `source_revision`.
6. Record run IDs, the Railway deployment ID and the `/build` SHA in
   `evidence/release-readiness/ledger.md`.

---

## Phase C — cleanup PR (after B3 passed)

1. `.github/workflows/ci.yml`: `branches: [main]` for `push` and `pull_request`.
2. `tests/test_release_workflow_contract.py`: `TRANSITIONAL_BRANCHES = ()`.
3. `CLAUDE.md`: "Repo Lineage & Branches", the deploy command (`git push origin main`)
   and the release-please caveat.
4. Session/branch rules that say `origin/master` (for example the sprint plans) point at `main`.
5. `evidence/release-readiness/live-production-gates.json`: `github_default_branch: "main"`
   with the evidence from B3.

---

## Rollback

| Situation | Action |
|-----------|--------|
| After B-rename | rename `main` back to `master` (same dialog); set Railway source back to `master` |
| After B-switch | set default back to `master`; set Railway source back to `master` |
| After phase C merged | revert the phase-C PR first, then the steps above |

CI keeps triggering on both names until phase C, so CI coverage holds during any rollback
before phase C.
