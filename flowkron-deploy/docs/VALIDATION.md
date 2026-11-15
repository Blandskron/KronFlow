# Validation

From the repository root run `docker compose config --quiet`. Start a disposable project with `docker compose -p flowkron-smoke up --build --wait`, then run `python flowkron-deploy/bootstrap/smoke.py flowkron-smoke`. The test requires the default local user and inserts synthetic data into the disposable workspace.

- Use `docker compose ps` to confirm health of IAM, Operational, Agent Core, the two frontends and the mail gateway.
- Verify IAM at `/healthz/`, Operational at `/readyz` and Agent Core at `/ready`.
- For the internal mail gateway use `/health` for liveness and `/ready` for provider and sender configuration.
- Test account verification, invitation and recovery with synthetic data and a mocked provider or an authorized Resend test environment.
