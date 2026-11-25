# Contributing

1. Open an issue describing the affected behavior and component. Report vulnerabilities through the [security policy](SECURITY.md).
2. Keep a change focused and include synthetic reproduction steps. Preserve documented API contracts, tenant isolation and persistent storage unless the change includes a migration.
3. Run the applicable checks and include their results in the pull request.

From each Angular component, run `npm ci` and `npm run build` with Node 24. The visual smoke tests use Playwright from their respective `tests/visual` directories.

Use Python 3.12 and separate environments for the Python services. Install each service's own requirements. Run `python manage.py check` and `python manage.py test` in IAM with `DJANGO_DEBUG=True` and no shared database. Use `python -m pytest` in Agent Core with `requirements-dev.txt`, and in the mail gateway with `requirements.txt`. For Operational, compile `app` and import `app.main`; exercise changes to provisioning against a disposable PostgreSQL database.

Run the three Python validators under [API Contracts scripts](flowkron-api-contracts/scripts) from the contract directory. Validate the integrated topology from the repository root with `docker compose --env-file .env.example config --quiet`.

Follow the [code of conduct](CODE_OF_CONDUCT.md). KronFlow (formerly Flowkron) is distributed under [Apache License 2.0](LICENSE).
