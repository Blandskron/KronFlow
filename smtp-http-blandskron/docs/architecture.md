# Arquitectura

```mermaid
flowchart LR
    Consumer[Consumidor autenticado] --> Gateway[Blandskron Email Gateway]
    Gateway --> Auth[Bearer interno y sender_key]
    Auth --> Service[EmailService]
    Service --> Idempotency[IdempotencyStore]
    Service --> Provider[EmailProvider]
    Provider --> Resend[Resend HTTPS API]
    Resend --> Recipient[Destinatarios]
    Resend --> Webhook[Eventos firmados]
    Webhook --> Audit[Auditoría segura]
```

Las capas están separadas en `app/security.py`, `app/service.py`, `app/email.py`, `app/resend_provider.py`, `app/idempotency.py` y `app/webhooks.py`.

## Estado e idempotencia

- Con `REDIS_URL`, las reservas y resultados idempotentes viven 24 horas en Redis.
- Sin `REDIS_URL`, se usa memoria local: reinicios y réplicas pierden la garantía
  compartida.
- La deduplicación de webhooks también es memoria local de proceso.

El servicio puede escalar horizontalmente de forma segura solo después de
configurar Redis para envíos y un almacenamiento compartido para eventos webhook.
