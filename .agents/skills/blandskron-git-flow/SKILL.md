---
name: blandskron-git-flow
description: Operational Git Flow standard (BLK-ENG-001 v1.0, Profile A) for KronFlow: branch naming, Conventional Commits, Pull Requests, quality gates, SemVer annotated releases, hotfix/rollback, and repository hygiene.
---

# Blandskron Git Flow Skill — KronFlow (`BLK-ENG-001` v1.0)

Apply this skill whenever creating branches, committing, opening or merging Pull Requests, cutting SemVer releases/tags, executing hotfixes/rollbacks, or auditing repository hygiene.

## 1. Active Profile & Topology

- **Active Profile:** **Profile A (Individual maintainer)** — `main` + short-lived branches + self-reviewed PR + green `Validate` CI. Zero external approvals required while maintained solo; never fabricate or simulate an independent approval. Promote to **Profile B** (1 independent human approval + `CODEOWNERS`) when additional maintainers join.
- **Permanent branch:** `main` only. Never create persistent `develop`, `qa`, or `staging` branches without a documented contractual exception.
- **Branch naming (lowercase ASCII, `kebab-case`, with work ID):**
  - `feature/<id>-<slug>` · `fix/<id>-<slug>` · `hotfix/<id>-<slug>`
  - `docs/<id>-<slug>` · `refactor/<id>-<slug>` · `test/<id>-<slug>` · `chore/<id>-<slug>`
  - `ci/<id>-<slug>` · `perf/<id>-<slug>` · `security/<id>-<slug>` · `spike/<id>-<slug>`
  - `release/<major>.<minor>` (on-demand only under Extension R for parallel maintenance)

## 2. Daily Cycle, Commits & PR Integration

1. Start from clean `main`: `git status --short && git switch main && git pull --ff-only origin main && git switch -c <type>/<id>-<slug>`.
2. Keep changes small and focused; review `git diff` and `git diff --cached` before committing; never stage `.env`, PEM keys, or real PII.
3. Use **Conventional Commits 1.0.0**: `type(scope): description` (`feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `build`, `ci`, `perf`, `style`, `revert`, `security`; `!` or `BREAKING CHANGE` for breaking changes).
4. Open a PR using `.github/pull_request_template.md` with task ID, scope, executed test evidence, security/data impact, and rollback notes.
5. Integrate via **Squash merge** once all `Validate` CI gates are green. Never force-push or rewrite `main`.

## 3. Releases (SemVer 2.0.0), Hotfixes & Rollback

- **Release from validated `main` SHA:**
  ```sh
  git switch main
  git pull --ff-only origin main
  # Confirm green CI on <SHA> before tagging
  git tag -a vX.Y.Z -m "Release vX.Y.Z" <SHA>
  git push origin vX.Y.Z
  ```
- Never move or overwrite a published release tag. Never release without explicit user authorization.
- **Hotfix:** If `main` is clean and releasable, branch `hotfix/<id>-<slug>` from `main` and merge via PR. If `main` has unreleased work, branch `release/<major>.<minor>` from the deployed tag, apply the fix via PR, tag `vX.Y.(Z+1)`, and forward-port to `main`.
- **Rollback:** Prefer `git revert <SHA>` in a `fix/<id>-revert-<slug>` PR over `reset` or force-push. For schema-breaking changes, follow the documented backup/restore + tombstone drill in `RELEASE_READINESS.md`.

## 4. Repository Hygiene & AI Agent Limits

- Keep `git config fetch.prune true` and auto-delete PR branches on merge.
- Delete merged local branches safely (`git branch -d <branch>`; before using `-D` after a squash merge, verify the PR is merged and has no unmerged commits). Never run bulk `-D`.
- Agents must never alter remote branch protections without authorization, approve their own PRs as independent reviewers, delete others' branches, or publish releases without explicit instruction.
