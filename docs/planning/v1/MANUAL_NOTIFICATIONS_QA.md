# Prueba manual de Notificaciones

Usa la demo local descartable. Carga el [fixture SQL de Contactos](MANUAL_CRM_QA.md#fixture-sql-opcional-para-las-pruebas-de-notificaciones) y elige **Iniciar seguimiento** en **Contacto QA sin lead**. El siguiente fixture agrega dos registros históricos sintéticos al schema de esa empresa. Uno enlaza al lead y otro simula un destino que ya no está disponible. La cola de atención depende del estado actual de las conversaciones, así que el fixture puede dejarla vacía.

Desde la raíz del repositorio, usa el mismo `$qaSchema` del recorrido anterior. Ajusta `operational_schema`, usuario y base si cambiaste los valores predeterminados de la demo.

```powershell
Get-Content -Raw flowkron-operational-service/tests/fixtures/manual_handoff_qa.sql |
  docker compose -f compose.demo.yaml exec -T flowkron-postgres psql -X -U flowkron_admin -d flowkron_auth `
    -v ON_ERROR_STOP=1 -v operational_schema=operational -v "tenant_schema=$qaSchema"
```

| Paso | Resultado esperado |
| --- | --- |
| Abre **Notificaciones → Historial**. | Aparecen dos derivaciones de entrada con fecha. El registro asociado a **Contacto QA sin lead** ofrece **Abrir lead**. El otro indica **Registro vinculado no disponible**. |
| Abre el lead y vuelve a Notificaciones. | El destino coincide con la ficha del contacto sintético. Al volver a Historial, se conservan los registros. |
| Cambia a **Pendientes**. | La vista muestra solo conversaciones en espera. Si existen, **Ver pendientes en Bandeja** abre el filtro de atención. |
| Ejecuta el fixture una segunda vez y recarga. | Siguen apareciendo los mismos dos registros sintéticos. |
| Entra a otra empresa de QA que carezca de los eventos. | El historial anterior queda fuera de esa empresa. |

La prueba automática adicional ejerce una derivación de WhatsApp con conversación visible y vuelve a consultar después de retirar esa conversación de la Bandeja. Ese caso verifica el enlace alternativo al lead sin usar una cuenta real. [Pruebas PostgreSQL](../../../flowkron-operational-service/tests/test_handoff_history.py)
