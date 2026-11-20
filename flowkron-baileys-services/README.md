# Flowkron Baileys Services

La ingestión conserva el ID real del proveedor en cada mensaje. Para una respuesta, registra el ID devuelto por su propio envío y el estado reportado `sent`; ese estado no confirma entrega ni lectura. Ver la [decisión de identidad de mensajes](../flowkron-operational-service/docs/MESSAGE_IDENTITY.md).

FK-02 persiste el turno en Operational y reutiliza respuestas preparadas al reintentar. FK-03 guarda consultas aceptadas en PostgreSQL y las retoma cuando se abre o restaura el socket de la cuenta original. FK-07 reserva el ID antes de enviar y transmite recibos directos de Baileys a Operational. Un recibo que coincida puede resolver un resultado incierto sin retransmitir. El conector de empresa requiere `tenant_schema_v8` antes de abrir tráfico. Ver [recuperación y reconciliación](../flowkron-operational-service/docs/TURN_RECOVERY.md).

En las sesiones de empresa, BAJA puede guardarse mientras el agente procesa un mensaje. Operational deduplica los comandos de consentimiento por identidad del mensaje. La garantía empieza cuando se guarda la decisión en Operational. Ver [retirada de consentimiento](../flowkron-operational-service/docs/TURN_RECOVERY.md#retirada-de-consentimiento).

Vincula una cuenta de WhatsApp por empresa en **WhatsApp → Generar código QR** dentro del CRM. Escanea el código desde **Dispositivos vinculados** en el teléfono. El código vigente aparece únicamente a miembros con el permiso de conexión de su empresa.

- El conector guarda las credenciales de cada empresa en su propio directorio dentro del volumen privado `baileys-lab-sessions`. Las sesiones vinculadas se reabren después de reiniciar el servicio.
- Los contactos aceptan el uso de sus datos escribiendo `ACEPTO`, y pueden retirarlo con `BAJA`. Las consultas posteriores se guardan en la base de datos de la empresa. El agente toma su contexto de **Contexto empresarial**. Cuando necesita intervención, la conversación aparece como pendiente de atención.
- En esta versión se procesan mensajes directos de texto. El conector debe tener una sola réplica por volumen y acceso a WhatsApp Web.

El servicio escucha en el puerto interno 3001. IAM valida la membresía antes de acceder a la sesión. Las rutas internas requieren el Bearer privado que genera Compose.

| Acción de IAM | Ruta del conector |
| --- | --- |
| Consultar estado y QR | `GET /internal/baileys/tenants/{id}/session` |
| Iniciar o retomar vínculo | `POST /internal/baileys/tenants/{id}/session` |
| Desconectar y eliminar las credenciales locales de esa sesión | `DELETE /internal/baileys/tenants/{id}/session` |

El estado privado de cada empresa incluye una causa normalizada, última conexión, hasta ocho transiciones recientes y el próximo intento de reconexión. El historial reside en el proceso actual. Después de cinco reintentos automáticos se puede iniciar otro ciclo sin borrar el vínculo. La pérdida de credenciales requiere volver a vincular. El QR solo se conserva en memoria y se oculta cuando vence, al cerrar el socket o al iniciar otro proceso.

El endpoint `GET /health` comprueba que el proceso HTTP responde. Los endpoints de laboratorio para una sola sesión siguen aceptando `BAILEYS_INGEST_TENANT_CODE` y `BAILEYS_INGEST_KEY`; la integración del CRM obtiene la empresa de IAM y usa sus propias rutas.

```sh
npm ci
npm test
```
