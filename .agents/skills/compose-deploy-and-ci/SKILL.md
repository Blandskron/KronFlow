---
name: compose-deploy-and-ci
description: Guidelines and verification workflows for KronFlow modular Docker Compose stacks (deploy/, compose.yaml, compose.demo.yaml), smoke tests, GitHub Actions CI (.github/workflows/validate.yml), and gitleaks secret scanning.
---

# Compose, Deploy & CI Skill — KronFlow

Use this skill whenever editing `deploy/`, `compose.yaml`, `compose.demo.yaml`, `.env.example`, `.github/workflows/`, or `.gitleaksignore`.

## 1. Deployment Topology Rules

- **Modular Compose:** Root `compose.yaml` and `compose.demo.yaml` include modular definitions under `deploy/compose/` (`bootstrap`, `infrastructure`, `backend`, `frontend`, `email`, `whatsapp`). Do not add Railway or PaaS-specific config files.
- **Zero-config fresh start:** A clean checkout must boot without a `.env` file; `deploy/compose/bootstrap.yml` (`init`) generates persistent project-scoped secrets in Docker volumes (`/bootstrap/*`, `/run/flowkron/*`).
- **Private vs Public mounts:** Never mount the IAM private JWT PEM into verification services (`operational-service`, `agent-core`); share only the read-only public key volume.
- **Browser-reachable frontend URLs:** Frontend build args (`API_PUBLIC_URL`, `OPERATIONAL_API_PUBLIC_URL`, `AGENT_CORE_API_PUBLIC_URL`, `APP_PUBLIC_URL`, `LANDING_PUBLIC_URL`, `CONTACT_API_BASE_URL`) must be reachable from the user's browser — never use internal Docker DNS names for them.
- **Loopback local defaults:** Local Compose binds to loopback for development; production requires explicit TLS, ingress rate limits, rotated secrets, and isolated backups.

## 2. Secret Safety & Validation

- **Never print expanded Compose config:** `docker compose config` prints resolved secrets. Always validate syntax silently:
  ```sh
  docker compose --env-file .env.example config --quiet
  docker compose -f compose.demo.yaml --env-file .env.example config --quiet
  ```
- **Destructive commands:** Never run `docker compose down -v` or `docker system prune` on persistent user environments without explicit approval.
- **Smoke verification (disposable project name):**
  ```sh
  docker compose -f compose.yaml -p kronflow-smoke up --build --wait --wait-timeout 180
  python deploy/bootstrap/smoke.py kronflow-smoke --standard
  docker compose -f compose.yaml -p kronflow-smoke down
  ```
- **Secret scan (exact CI parity):**
  ```powershell
  docker run --rm -v "${PWD}:/repo" zricethezav/gitleaks:v8.30.1 git --redact=100 --no-banner --log-opts='--all' /repo
  ```
  If a verified non-secret test fixture triggers a historical false positive, document its exact fingerprint in `.gitleaksignore` rather than rewriting pushed `main` history.
