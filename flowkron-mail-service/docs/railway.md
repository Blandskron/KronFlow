# Railway

Configura las variables secretas directamente en Railway: `RESEND_API_KEY`,
`RESEND_WEBHOOK_SECRET`, `EMAIL_SENDERS_JSON` e `INTERNAL_CLIENTS_JSON`. Añade los
límites, `ENABLE_LEGACY_MAIL_ENDPOINT=false` y `REDIS_URL` para idempotencia
persistente.

Comando:

```bash
uvicorn app.main:app --host 0.0.0.0 --port "\${PORT:-8000}" --proxy-headers --forwarded-allow-ips="*"
```

Healthcheck: `/health`. Readiness: `/ready`. El servicio no necesita puertos SMTP.
El healthcheck no sustituye una prueba de envío ni la verificación de eventos del
proveedor.
