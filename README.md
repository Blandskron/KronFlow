# Flowkron

**CRM inteligente para WhatsApp · by BLANDSKRON**

Flowkron brings a conversation inbox, lead tracking, operational metrics, team management and an AI context simulator into a multi-tenant workspace. Connect WhatsApp by scanning a QR code in the CRM. Each workspace manages its own connection and agent context.

Flowkron is independent and has no affiliation with or endorsement from Meta or WhatsApp. Flowkron is open source under [Apache License 2.0](LICENSE). See the [release review](RELEASE_READINESS.md) for verification and deployment scope.

The repository currently provides a source preview and local demo. Before hosting it for other organizations, follow the [deployment security guide](flowkron-deploy/docs/SECURITY.md). See [third-party components](THIRD_PARTY.md) before distributing container images.

## Start locally

Use Docker Desktop or Docker Engine with the Docker Compose plugin. From the repository root, start the full local stack:

```sh
docker compose up --build --wait
```

A fresh checkout can start without an `.env`. The init job generates instance credentials and keeps them in Docker volumes. Add a private `.env` based on [the example](.env.example) only for overrides or external providers.

On Windows, clone into a short directory path if Git reports `Filename too long` while checking out the Angular sources.

| Surface | Default address |
| --- | --- |
| Landing and contact | http://localhost:8080 |
| CRM | http://localhost:8081 |
| IAM health | http://localhost:8000/healthz/ |
| Operational health | http://localhost:8001/healthz |
| Agent Core health | http://localhost:8002/health |
| Email gateway | Internal address at `http://smtp-http-blandskron:8000` |

### Start from scratch

Open the landing or the CRM, create and verify your account, and register your company. Flowkron provisions the company's isolated database schema during setup and opens the workspace without a plan selection. Go to **WhatsApp** to link a device and **Contexto empresarial** to add products and policies. The standard deployment starts without an administrator or demo company.

### Start the demo

Run the demo separately from the standard deployment. Both use the same host ports by default.

```sh
docker compose -f compose.demo.yaml up --build --wait
```

On its first local start, the demo creates the verified Django superuser `admin@example.com` as owner of **BLANDSKRON** and loads a generic business context for the agent. Sign in to the [CRM](http://localhost:8081/login) or [Django admin](http://localhost:8000/admin/). Retrieve its generated password in your private terminal:

```sh
docker compose -f compose.demo.yaml exec -T flowkron-auth-service cat /run/flowkron/bootstrap_admin_password
```

Console mail, local agent responses and the WhatsApp connector work with no provider credentials for a local install. If you need email delivery to real inboxes, configure the transactional provider below. See the [deployment guide](flowkron-deploy/README.md) for ports, persistence and server configuration.

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

- **WhatsApp** pairs one account per workspace using the QR in the CRM. The [Baileys connector](flowkron-baileys-services/README.md) records consent, stores text conversations and relays replies from Agent Core.
- **AI** in Agent Core can use Groq or local context. Set `GROQ_API_KEY` in your private `.env` and recreate Agent Core to use Groq with the default `CHAT_PROVIDER=auto`. See the [configuration guide](flowkron-agent-core/docs/CONFIGURATION.md) for model selection and local mode.
- **Operating costs** depend on the infrastructure, messaging, email and AI providers selected by the instance operator.

## Develop and contribute

- [Architecture and component links](ARCHITECTURE.md)
- [Local validation and contribution guide](CONTRIBUTING.md)
- [Migration and change history](CHANGELOG.md)
- [Análisis y tareas de evolución de Flowkron](EVOLUCION_FLOWKRON.md)
- [Responsible disclosure](SECURITY.md)
- [Brand assets](assets/brand/README.md)

### Inicio rápido en español

Ejecuta `docker compose up --build --wait` desde la raíz, registra tu cuenta y crea tu empresa. Para probar con la cuenta administradora de BLANDSKRON y el agente de ejemplo, usa `docker compose -f compose.demo.yaml up --build --wait`.
