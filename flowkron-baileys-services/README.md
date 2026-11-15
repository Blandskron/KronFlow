# Flowkron Baileys Services

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

El endpoint `GET /health` comprueba que el proceso HTTP responde. Los endpoints de laboratorio para una sola sesión siguen aceptando `BAILEYS_INGEST_TENANT_CODE` y `BAILEYS_INGEST_KEY`; la integración del CRM obtiene la empresa de IAM y usa sus propias rutas.

```sh
npm ci
npm test
```
