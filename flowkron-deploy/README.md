# Local deployment

The root [Compose entry point](../compose.yaml) includes this directory. Run `docker compose up --build --wait` from the root. A new local project provisions IAM, Operational, Agent Core, both Angular apps, PostgreSQL, Redis, the mail gateway and Baileys. See [first login and provider setup](../README.md) and the [upgrade notes](../CHANGELOG.md).

- `compose/infrastructure.yml` defines PostgreSQL and Redis.
- `compose/backend.yml` builds IAM, Operational and Agent Core and shares IAM's public signing key.
- `compose/frontend.yml` builds the public landing and CRM.
- `compose/email.yml` runs the email gateway on the internal Compose network. It shares Redis in DB 1.
- `compose/whatsapp.yml` runs the [Baileys connector](../flowkron-baileys-services/README.md) on the internal network. It starts disconnected.
- `.env.example` shows optional overrides when launching directly from this directory. The root example has the same values.

Validate either entry point with `docker compose config --quiet`. If a local port is occupied, copy the example to `.env` and change the port. Compose derives local frontend URLs and CORS defaults from the ports. Keep the named volumes across restarts. To serve other machines, configure your public URLs, allowed hosts, CORS, and TLS at your proxy. The generated workspace is restricted to loopback and Django debug mode.
- `compose/bootstrap.yml` prepares persistent settings for the services before they start.
