# Contributing

1. Open an issue describing the affected behavior and component. Report vulnerabilities through the [security policy](SECURITY.md).
2. Keep a change focused and include synthetic reproduction steps. Preserve documented API contracts, tenant isolation and persistent storage unless the change includes a migration.
3. Run the applicable checks and include their results in the pull request.

From `frontend/app` and `frontend/landing`, run `npm ci`, `npm run lint`, `npm test` and `npm run build` with Node 24. The visual smoke tests use Playwright from their respective `tests/visual` directories. From `backend/baileys-services`, run `npm ci` and `npm test`.

Use Python 3.12 and separate environments for the Python services under `backend/`: run `python manage.py check` and `python manage.py test` in `backend/auth-service` with `DJANGO_DEBUG=True` and no shared database; use `python -m pytest` in `backend/agent-core` with `requirements-dev.txt` and in `backend/mail-service` with `requirements.txt`. For `backend/operational-service`, run the unittest suite against PostgreSQL 18 and verify `from app.main import app; assert app.openapi()["paths"]`.

Validate both integrated Compose topologies from the repository root with `docker compose --env-file .env.example config --quiet` and `docker compose -f compose.demo.yaml --env-file .env.example config --quiet`.

Follow the [code of conduct](CODE_OF_CONDUCT.md). KronFlow (formerly Flowkron) is distributed under [Apache License 2.0](LICENSE).
