# Validation

From the repository root run `docker compose --env-file .env.example config --quiet`. Start a disposable stack for integration checks.

- Use `docker compose ps` to confirm health of IAM, Operational, Agent Core, the two frontends and the mail gateway.
- Verify IAM at `/healthz/`, Operational at `/healthz` and Agent Core at `/health`.
- For the internal mail gateway use `/health` for liveness and `/ready` for provider and sender configuration.
- Test account verification, invitation and recovery with synthetic data and a mocked provider or an authorized Resend test environment.
