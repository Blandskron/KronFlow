# Configuration

Use [the environment reference](../.env.example) for local ports, database names, independent API URLs, signing keys and optional Azure OpenAI settings. Run Compose with an explicit private env file when it is kept outside the repository root.

IAM requires the same internal credential as Operational. Keep the signing key encryption secret and the signing key data stable between updates. Override `FLOWKRON_DATA_DIR` to put IAM media and signing keys outside the deployment tree.

The default development mail backend writes to the IAM console. To configure authenticated HTTP mail and a Resend sender, follow the [transactional email instructions](../../README.md#enable-transactional-email).
