# Operations

Start, inspect and stop the local stack from the repository root.

```powershell
docker compose config --quiet
docker compose up --build --wait
docker compose ps
docker compose logs --tail 100 flowkron-auth-service flowkron-mail-service
docker compose down
```

Preserve the existing PostgreSQL and Redis volumes, IAM media and signing keys when upgrading. See the [migration instructions](../../CHANGELOG.md#migrate-a-prior-deployment). Keep private logs and local email messages out of shared issue reports.
