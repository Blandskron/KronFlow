---
name: docs-and-agents-protocol
description: Rules for maintaining KronFlow's minimalist Agents-First, Human-Friendly documentation structure (root docs + one README.md per backend service, frontend app, and deploy/) without doc sprawl, broken links, or drift from real code.
---

# Documentation & Agents-First Protocol Skill — KronFlow

Use this skill whenever adding, editing, or auditing markdown files or agent skills in KronFlow.

## 1. Allowed Documentation Layout

Keep documentation lean, factual, and zero-duplication:

- **Initial / Root docs:** `README.md`, `ARCHITECTURE.md`, `AGENTS.md`, `RELEASE_READINESS.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`, `THIRD_PARTY.md`, `CODE_OF_CONDUCT.md`, `LICENSE`, `NOTICE`, `assets/brand/README.md`.
- **Per backend microservice (1 file each):** `backend/<service>/README.md`.
- **Per frontend app (1 file each):** `frontend/<app>/README.md`.
- **Deployment (1 file):** `deploy/README.md`.
- **Agent skills:** `.agents/skills/<skill-name>/SKILL.md` (and root `.github/copilot-instructions.md` pointing to `AGENTS.md`).
- **Static assets only in `docs/`:** `docs/screenshots/` (referenced by `README.md` and `index.html`).

**Do NOT create:**
- Per-service `docs/` folders, per-service `AGENTS.md`, per-service `.github/`, or per-service `skills/`.
- Planning snapshots, historical audit dumps, or PaaS-specific guides (e.g., Railway).

## 2. Agents-First, Human-Friendly Writing Rules

1. **Code is ground truth:** Before documenting a route, env var, schema version, or command, verify it directly in source code or `.github/workflows/validate.yml`.
2. **High signal, low fluff:** Prefer compact tables (routes, env vars, commands, ports) and exact runnable commands over long prose.
3. **Explicit limits:** Clearly distinguish implemented behavior from external operational gates (real accounts/sandboxes/backups).
4. **Zero broken links:** After any doc edit or deletion, verify that every relative markdown link resolves to an existing file in the repo.
5. **No secrets or PII:** Use synthetic placeholders (`replace-with-*`, `example.com`) only.
