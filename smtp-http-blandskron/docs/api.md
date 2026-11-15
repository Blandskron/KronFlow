# API

El endpoint principal es `POST /api/v1/emails/send` y exige Bearer interno.

Payload:

```json
{
  "sender_key": "blandskron",
  "to": ["destinatario@example.com"],
  "subject": "Asunto",
  "html": "<p>HTML</p>",
  "text": "Texto",
  "reply_to": null,
  "idempotency_key": "example1"
}
```

El remitente real y el reply-to autorizado se resuelven desde `EMAIL_SENDERS_JSON`. Respuestas: 200 aceptado, 401/403 seguridad, 422 validación, 409 operación en proceso, 429 rate limit, 502 proveedor.

Diagnóstico de seguridad:

- `401 AUTH_REQUIRED`: el consumidor no envió `Authorization: Bearer`.
- `401 AUTH_INVALID`: el Bearer no coincide con ningún cliente activo de `INTERNAL_CLIENTS_JSON`.
- `403 SENDER_FORBIDDEN`: el cliente existe, pero `sender_key` no figura en `allowed_senders`.
- `503 NOT_READY` en `/ready`: faltan `RESEND_API_KEY`, remitentes o clientes internos.

`POST /mail` queda deprecated y solo acepta `senderKey`, `to`, `subject`, `text`, `attachedHtml`, `replyTo` e `idempotencyKey`; nunca campos SMTP.

## Idempotencia

`idempotency_key` es obligatoria. Una repetición devuelve el resultado almacenado
si está disponible; una operación todavía en curso puede responder `409`. La
garantía es compartida entre instancias únicamente cuando el gateway usa Redis.
