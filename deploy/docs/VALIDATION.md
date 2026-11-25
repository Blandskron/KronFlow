# Validation

From the repository root run `docker compose config --quiet`. Use one disposable project at a time, or give each separate host ports. Do not run these checks against an existing instance.

| Cold start | Start command | Smoke command |
| --- | --- | --- |
| Standard | `docker compose -p flowkron-smoke-standard up --build --wait` | `python flowkron-deploy/bootstrap/smoke.py flowkron-smoke-standard --standard` |
| Demo | `docker compose -f compose.demo.yaml -p flowkron-smoke-demo up --build --wait` | `python flowkron-deploy/bootstrap/smoke.py flowkron-smoke-demo` |

The standard smoke uses console email and both variants insert synthetic data. Stop each project using the same Compose file and project name with `down`.

- Use `docker compose ps` to confirm health of IAM, Operational, Agent Core, the two frontends and the mail gateway.
- Verify IAM at `/healthz/`, Operational at `/readyz` and Agent Core at `/ready`.
- For the internal mail gateway use `/health` for liveness and `/ready` for provider and sender configuration.
- Test account verification, invitation and recovery with synthetic data and a mocked provider or an authorized Resend test environment.
