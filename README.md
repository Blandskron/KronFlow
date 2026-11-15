# Flowkron

**CRM inteligente para WhatsApp · by BLANDSKRON**

Flowkron brings a conversation inbox, lead tracking, operational metrics, team management and an AI context simulator into a multi-tenant workspace. The HTTP ingestion API accepts normalized WhatsApp events from an external adapter.

Flowkron is independent and has no affiliation with or endorsement from Meta or WhatsApp. Flowkron is open source under [Apache License 2.0](LICENSE). See the [release review](RELEASE_READINESS.md) for verification and deployment scope.

## Start locally

Use Docker Desktop or Docker Engine with the Docker Compose plugin. From the repository root, start the full local stack:

```sh
docker compose up --build --wait
```

A fresh checkout can start without an `.env`. The init job generates instance credentials and keeps them in Docker volumes. Add a private `.env` based on [the example](.env.example) only for overrides or external providers.

| Surface | Default address |
| --- | --- |
| Landing and contact | http://localhost:8080 |
| CRM | http://localhost:8081 |
| IAM health | http://localhost:8000/healthz/ |
| Operational health | http://localhost:8001/healthz |
| Agent Core health | http://localhost:8002/health |
| Email gateway | Internal address at `http://smtp-http-blandskron:8000` |

On a fresh local database, Compose creates the verified Django superuser `admin@example.com` as the owner of the **BLANDSKRON** workspace and provisions its CRM schema. The same generated password works in the [CRM](http://localhost:8081/login) and the [Django admin](http://localhost:8000/admin/). Retrieve it in your private terminal:

```sh
docker compose exec -T flowkron-auth-service cat /run/flowkron/bootstrap_admin_password
```

For a custom initial administrator, set `DJANGO_SUPERUSER_EMAIL` in the private `.env`. To supply a password, set `CREATE_SUPERUSER=True` and `DJANGO_SUPERUSER_PASSWORD` before the first start. `DJANGO_SUPERUSER_USERNAME` is optional and applies to Django admin, while the CRM uses the email. Existing accounts keep their passwords across restarts.

Console mail, local agent responses, and an unlinked Baileys service are available with zero provider credentials. Existing installations should follow the [migration notes](CHANGELOG.md#migrate-a-prior-deployment). See the [deployment guide](flowkron-deploy/README.md) for host ports, persistence and server configuration.

## Configure account registration and Google sign-in

The CRM supports email registration and Google sign-in. Email registration sends a verification link to the address entered, then lets the recipient choose a password. Configure transactional email for real delivery. With the local console backend, the link is written to the IAM container logs.

- Set `GOOGLE_OAUTH_CLIENT_ID` in the private root `.env` to the Google OAuth client ID for a **Web application**. An empty value hides the Google button.
- In Google Cloud, add `http://localhost` and `http://localhost:8081` to **Authorized JavaScript origins** for Docker development. If you use a different CRM port, add that exact origin. For a hosted CRM, add its exact HTTPS origin. Apply **Flowkron** branding in Google Auth Platform. [Google Identity Services setup](https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid)
- Flowkron uses the Google Identity Services popup callback. Leave **Authorized redirect URIs** empty for a client dedicated to Flowkron. The server validates Google's ID token and uses the `sub` claim to identify the account. This flow uses the public client ID. [Google ID token verification](https://developers.google.com/identity/gsi/web/guides/verify-google-id-token)
- Set `AUTH_SELF_SIGNUP_ENABLED=False` if this instance should accept only existing users and invitations. Existing Google-linked accounts can still sign in when the client ID remains configured.

Apply the configuration and account migration with `docker compose up --build --wait`. If you host the frontends on custom domains, set `APP_PUBLIC_URL` to the CRM URL and include the CRM and landing origins in `CORS_ALLOWED_ORIGINS`.

## Enable transactional email

The included [Blandskron gateway](smtp-http-blandskron/README.md) sends email through Resend. Set the following values in your private environment file.

```dotenv
EMAIL_BACKEND=apps.shared.email_backend.EmailGatewayBackend
MAIL_GATEWAY_URL=http://smtp-http-blandskron:8000
MAIL_INTERNAL_API_KEY=replace-with-a-generated-client-secret
MAIL_SENDER_KEY=flowkron
EMAIL_TIMEOUT=25
RESEND_API_KEY=
EMAIL_SENDERS_JSON='{"flowkron":{"from":"Flowkron <no-reply@example.com>"}}'
INTERNAL_CLIENTS_JSON='{"iam":{"api_key":"replace-with-a-generated-client-secret","allowed_senders":["flowkron"]}}'
```

Set a valid provider key and replace the example sender with an address on your verified sending domain. The IAM client key must match the gateway client entry. The gateway's `/health` checks process liveness and `/ready` checks configuration. An existing SMTP deployment can keep its explicitly configured Django SMTP backend and settings. An externally hosted gateway can be set through `MAIL_GATEWAY_URL` using HTTPS.

## Connect a channel or AI provider

- **WhatsApp** accepts normalized events through the [tenant-scoped ingest interface](flowkron-operational-service/docs/API.md). The included [Baileys lab connector](flowkron-baileys-services/README.md) starts disconnected, pairs one account via QR and can forward text from contacts with recorded consent. See the [integration research](flowkron-product-docs/04-architecture/14-whatsapp-connection-and-campaigns.md) for the onboarding, agent and campaign design.
- **AI** in Agent Core can use Groq or local context. Set `GROQ_API_KEY` in your private `.env` and recreate Agent Core to use Groq with the default `CHAT_PROVIDER=auto`. See the [configuration guide](flowkron-agent-core/docs/CONFIGURATION.md) for model selection and local mode.
- **Operating costs** depend on the infrastructure, messaging, email and AI providers selected by the instance operator.

## Develop and contribute

- [Architecture and component links](ARCHITECTURE.md)
- [Local validation and contribution guide](CONTRIBUTING.md)
- [Migration and change history](CHANGELOG.md)
- [Responsible disclosure](SECURITY.md)
- [Brand assets](assets/brand/README.md)

### Inicio rápido en español

Ejecuta `docker compose up --build --wait` desde la raíz. Abre el CRM en el puerto 8081 con `admin@example.com` y recupera la contraseña generada con el comando anterior. Configura un `.env` privado cuando necesites cambiar puertos o habilitar proveedores.
