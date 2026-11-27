# Contributing

## Git Flow & Branching Protocol (`BLK-ENG-001` v1.0)

This repository follows the **Blandskron Git Flow standard (`BLK-ENG-001` v1.0)** under **Profile A (Individual maintainer)**:

- **Single permanent branch:** `main` is the only permanent branch and must always remain buildable and releasable. `develop`, `qa`, and `staging` branches are not used.
- **Profile A (current — single maintainer):** Every change originates in a short-lived branch from up-to-date `origin/main` and integrates via Pull Request with self-review of the diff and green CI (`Validate`). Zero external approvals are required while maintained solo; never simulate an independent review. When additional maintainers join, promote this repository to **Profile B** (minimum 1 independent human approval + `CODEOWNERS`).
- **Branch naming (lowercase ASCII, `kebab-case`, work identifier):**
  - `feature/<id>-<slug>` — new functional capability
  - `fix/<id>-<slug>` / `hotfix/<id>-<slug>` — ordinary fix or urgent production fix
  - `docs/<id>-<slug>` · `refactor/<id>-<slug>` · `test/<id>-<slug>` · `chore/<id>-<slug>`
  - `ci/<id>-<slug>` · `perf/<id>-<slug>` · `security/<id>-<slug>` · `spike/<id>-<slug>`
  - `release/<major>.<minor>` — on-demand only (Extension R) when parallel maintenance of a published line is required
- **Commits & Merge Strategy:** Follow [Conventional Commits 1.0.0](https://www.conventionalcommits.org/) (`feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `build`, `ci`, `perf`, `style`, `revert`, `security`; `!` or `BREAKING CHANGE` for incompatible changes). Use **Squash merge** by default via PR; never push or merge directly to `main` from CLI during normal work.
- **Repository hygiene:** Enable automatic branch deletion on PR merge, keep `git config fetch.prune true`, and delete merged local/remote branches immediately after integration (never run bulk `git branch -D`).
- **Releases & Hotfixes (SemVer 2.0.0):** Tag annotated releases (`git tag -a vX.Y.Z -m "Release vX.Y.Z" <validated-SHA>`) strictly from a green-CI commit on `main`. Never modify a published tag. If `main` has unreleased changes during a production incident, cut a maintenance branch (`release/<major>.<minor>`) from the deployed tag, fix via PR, tag `vX.Y.(Z+1)`, and forward-port to `main`.

## Development & Verification Workflow

1. Open an issue describing the affected behavior and component. Report vulnerabilities through the [security policy](SECURITY.md).
2. Keep a change focused and include synthetic reproduction steps. Preserve documented API contracts, tenant isolation and persistent storage unless the change includes a migration.
3. Run the applicable checks and include their results in the pull request.

From `frontend/app` and `frontend/landing`, run `npm ci`, `npm run lint`, `npm test` and `npm run build` with Node 24. The visual smoke tests use Playwright from their respective `tests/visual` directories. From `backend/baileys-services`, run `npm ci` and `npm test`.

Use Python 3.12 and separate environments for the Python services under `backend/`: run `python manage.py check` and `python manage.py test` in `backend/auth-service` with `DJANGO_DEBUG=True` and no shared database; use `python -m pytest` in `backend/agent-core` with `requirements-dev.txt` and in `backend/mail-service` with `requirements.txt`. For `backend/operational-service`, run the unittest suite against PostgreSQL 18 and verify `from app.main import app; assert app.openapi()["paths"]`.

Validate both integrated Compose topologies from the repository root with `docker compose --env-file .env.example config --quiet` and `docker compose -f compose.demo.yaml --env-file .env.example config --quiet`.

Follow the [code of conduct](CODE_OF_CONDUCT.md). KronFlow (formerly Flowkron) is distributed under [Apache License 2.0](LICENSE).
