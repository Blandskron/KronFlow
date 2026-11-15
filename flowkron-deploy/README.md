# Local deployment

The root [Compose entry point](../compose.yaml) includes this directory. Follow the [root setup and email instructions](../README.md) and the [upgrade notes](../CHANGELOG.md). This stack runs IAM, Operational, Agent Core, the two Angular applications, PostgreSQL, Redis and the Blandskron email gateway.

- `compose/infrastructure.yml` defines PostgreSQL and Redis.
- `compose/backend.yml` builds IAM, Operational and Agent Core and shares IAM's public signing key.
- `compose/frontend.yml` builds the public landing and CRM.
- `compose/email.yml` runs the email gateway on the internal Compose network. It shares Redis in DB 1.
- `compose/whatsapp.yml` adds the optional `whatsapp-lab` profile for the [Baileys connector](../flowkron-baileys-services/README.md).
- `.env.example` describes development configuration when launching directly from this directory. The root example has the same values.

From this directory, validate the stack using `docker compose --env-file .env.example config --quiet`. From the root, use `docker compose` with a local `.env`.
