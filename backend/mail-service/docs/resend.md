# Resend

El proveedor está abstraído por `EmailProvider` en `app/email.py` e implementado por `ResendEmailProvider` en `app/resend_provider.py`.

La API utiliza HTTPS, timeout configurable, reintentos limitados con backoff y jitter, header `Idempotency-Key` y respuestas filtradas. Los errores permanentes no se reintentan.

Configura en el entorno:

- `RESEND_API_KEY`: secreto.
- `RESEND_BASE_URL`: normalmente `https://api.resend.com`.
- `RESEND_TIMEOUT_SECONDS`.
- `RESEND_WEBHOOK_SECRET`: secreto opcional para validar eventos.

Solo configura remitentes de dominios verificados en Resend.
