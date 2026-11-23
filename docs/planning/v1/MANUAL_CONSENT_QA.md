# Prueba manual del consentimiento de WhatsApp

Usa una demo descartable con WhatsApp desconectado y una cuenta de la empresa de QA con `users.read` y `audit.read`. Puedes comprobar el estado **Sin vínculo de WhatsApp** en cualquier contacto creado manualmente. [Alta desde la interfaz](MANUAL_CRM_QA.md#crear-el-contacto-desde-la-interfaz)

## Cargar el contacto sintético

Desde la raíz del repositorio, consulta el schema de la empresa de QA y reemplaza el valor de `$qaSchema` por el resultado exacto. Los comandos usan la configuración predeterminada de la demo. El fixture conserva el registro si se vuelve a ejecutar.

```powershell
docker compose -f compose.demo.yaml exec -T flowkron-postgres psql -X -U flowkron_admin -d flowkron_auth `
  -c 'SELECT tenant_slug, schema_name FROM operational.tenant_runtime WHERE status = ''active'';'

$qaSchema = 'tenant_REEMPLAZAR'
Get-Content -Raw flowkron-operational-service/tests/fixtures/manual_whatsapp_consent_qa.sql |
  docker compose -f compose.demo.yaml exec -T flowkron-postgres psql -X -U flowkron_admin -d flowkron_auth `
    -v ON_ERROR_STOP=1 -v "tenant_schema=$qaSchema"
```

## Verificar desde Contactos

| Paso | Resultado esperado |
| --- | --- |
| Busca **Contacto QA WhatsApp**, abre la ficha y pulsa **Consultar consentimiento**. | Aparece **Autorización vigente**, con la última decisión, la fecha desde la que rige y la política `v1.0`. Las fechas se muestran en la hora local del navegador. |
| Revisa el evento más reciente. | Dice **Baja de un periodo anterior**. La fecha de decisión es anterior a la última autorización y la de registro es posterior. |
| Pulsa **Ver eventos anteriores** y luego **Más recientes**. | El historial cambia de página y el estado vigente se conserva. |
| Abre un contacto manual con teléfono guardado y consulta el consentimiento. | Aparece **Sin vínculo de WhatsApp**. |
| Abre la ficha con una cuenta que solo tenga `users.read`. | Puedes abrir la ficha. La sección de consentimiento requiere `audit.read`. |

Registra el SHA, el rol y el resultado de cada paso. La autorización de envíos por finalidad se verifica en el gate de campañas. [Criterios de release](RELEASE_GATES.md)
