# documentation-audit

Use this skill when auditing or updating repository documentation.

Checklist:

1. Confirm `README.md`, `AGENTS.md`, `CLAUDE.md`, `GEMINI.md` and `docs/agent/*` still match code.
2. Check endpoint names against FastAPI routes.
3. Check config names against `app/core/config.py`.
4. Check models against `app/models`.
5. Record unverified assumptions in `docs/agent/DISCOVERY.md`.
