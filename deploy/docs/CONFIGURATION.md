# Configuration

Use [the environment reference](../.env.example) for local ports, database names, independent API URLs, signing keys and optional Groq settings. Run Compose with an explicit private env file when it is kept outside the repository root.

The init job generates credentials for a fresh project and reuses them from the same volumes. Put explicit existing credentials in the private environment before upgrading. Use `FLOWKRON_JWT_MOUNT` and `FLOWKRON_MEDIA_MOUNT` to reuse existing storage. Back up the PostgreSQL, IAM configuration, JWT and media volumes together. See the [migration notes](../../CHANGELOG.md#migrate-a-prior-deployment).

The default development mail backend writes to the IAM console. To configure authenticated HTTP mail and a Resend sender, follow the [transactional email instructions](../../README.md#enable-transactional-email).
