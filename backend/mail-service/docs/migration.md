# Migración desde SMTP

Antes, `/mail` aceptaba credenciales SMTP y el remitente en cada request. Ahora:

1. Configura un `sender_key` autorizado.
2. Configura un cliente interno independiente.
3. Cambia el consumidor a `POST /api/v1/emails/send`.
4. Envía Bearer interno.
5. Envía destinatarios como lista y una `idempotency_key`.
6. Elimina variables SMTP de consumidores y despliegues.
7. Mantén `ENABLE_LEGACY_MAIL_ENDPOINT=true` solo durante la transición.
8. Desactiva legacy después de migrar todos los consumidores.

KronFlow IAM usa `apps/shared/email_backend.py` y el endpoint nuevo. Consulta la [configuración](../../../README.md#correo-transaccional).
