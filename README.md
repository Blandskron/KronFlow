# Flowkron

**CRM inteligente para WhatsApp · by BLANDSKRON**

Flowkron brings a conversation inbox, lead tracking, operational metrics, team management and an AI context simulator into a multi-tenant workspace. The HTTP ingestion API accepts normalized WhatsApp events from an external adapter.

Flowkron is independent and has no affiliation with or endorsement from Meta or WhatsApp. Flowkron is open source under [Apache License 2.0](LICENSE). See the [release review](RELEASE_READINESS.md) for verification and deployment scope.

## Start locally

Use Docker Desktop or Docker Engine with a current Docker Compose plugin. Copy the sample environment and replace the development passwords and signing secrets before use outside an isolated local environment.

```powershell
Copy-Item .env.example .env
docker compose config --quiet
docker compose up --build --wait
```

| Surface | Default address |
| --- | --- |
| Landing and contact | http://localhost:8080 |
| CRM | http://localhost:8081 |
| IAM health | http://localhost:8000/healthz/ |
| Operational health | http://localhost:8001/healthz |
| Agent Core health | http://localhost:8002/health |
| Email gateway | Internal address at `http://smtp-http-blandskron:8000` |

To sign in to a new stack, set `CREATE_SUPERUSER=True` and provide a synthetic `DJANGO_SUPERUSER_EMAIL`, matching `DJANGO_SUPERUSER_USERNAME`, and a strong local password in `DJANGO_SUPERUSER_PASSWORD`. Recreate the IAM service once, then turn off automatic superuser setup. In the sample configuration, verification and recovery messages appear in the IAM container console. Use synthetic email addresses and keep those logs local.

```powershell
docker compose logs --tail 60 flowkron-auth-service
```

The first run applies Django migrations and seeds roles and the plan catalog. Tenant activation and provisioning still enforce the existing IAM and Operational plan rules. Access to an operational workspace requires an active non-free tenant runtime. The CRM shows the current access state. See the [IAM setup guide](flowkron-auth-service/docs/DEPLOYMENT.md) for operator commands and [Operational API](flowkron-operational-service/docs/API.md) for provisioning and ingestion. The [synthetic seed script](flowkron-operational-service/scripts/seed_demo_tenant.sql) targets an existing disposable tenant and is opt-in.

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

- **WhatsApp** uses an external adapter that owns Meta credentials, webhook authentication, consent and outbound delivery. Forward normalized events to the [tenant-scoped ingest interface](flowkron-operational-service/docs/API.md) using the provisioned tenant code and ingest key. The inbox is read-only. The previous bundled automation also handled calendar events and consent flows. Those features require an external implementation.
- **AI** in Agent Core can run its local fallback or use the optional Azure OpenAI configuration in [the environment example](.env.example). Verify the provider settings against the [Agent Core configuration guide](flowkron-agent-core/docs/CONFIGURATION.md).
- **Operating costs** depend on the infrastructure, messaging, email and AI providers selected by the instance operator.

## Develop and contribute

- [Architecture and component links](ARCHITECTURE.md)
- [Local validation and contribution guide](CONTRIBUTING.md)
- [Migration and change history](CHANGELOG.md)
- [Responsible disclosure](SECURITY.md)
- [Brand assets](assets/brand/README.md)

### Inicio rápido en español

Copia `.env.example` a `.env`, configura los secretos locales y ejecuta `docker compose up --build --wait`. Abre el CRM en el puerto 8081. El ejemplo registra el correo de verificación en el contenedor de IAM. Para enviar correo real, configura el remitente verificado y las credenciales del gateway.
