# Prueba manual de la bandeja de privacidad

Usa una empresa de una demo local descartable. El caso sintético permite verificar permisos, filtro y registro de cierre. La pantalla registra el estado del trámite. Las acciones sobre los datos se ejecutan en el proceso autorizado de la empresa.

Para cargar una solicitud, reutiliza `$qaSchema` de la [guía CRM](MANUAL_CRM_QA.md#fixture-sql-opcional-para-las-pruebas-de-notificaciones):

```powershell
@'
INSERT INTO :"tenant_schema".solicitudes_derechos (whatsapp_id, tipo_derecho)
SELECT 'qa-privacy-01', 'acceso'
WHERE NOT EXISTS (
  SELECT 1 FROM :"tenant_schema".solicitudes_derechos
  WHERE whatsapp_id = 'qa-privacy-01' AND tipo_derecho = 'acceso'
);
'@ | docker compose -f compose.demo.yaml exec -T flowkron-postgres psql -X -U flowkron_admin -d flowkron_auth `
  -v ON_ERROR_STOP=1 -v "tenant_schema=$qaSchema"
```

| Acción | Resultado esperado |
| --- | --- |
| Entra a **Configuración → Solicitudes de privacidad** con `audit.read`. | Aparece una solicitud de acceso pendiente con fecha de entrada y límite registrado. La ficha de la cola omite el identificador de canal y las notas. |
| Con `audit.read` y `crm.manage`, pulsa **Iniciar revisión** y filtra **En revisión**. | Aparece la misma solicitud en revisión. |
| Pulsa **Registrar cierre** sin confirmar. Luego registra el cierre del caso sintético con la casilla marcada. | La primera acción no envía el cambio. La segunda registra el cierre con fecha y mueve el caso a **Completadas**. |
| Repite con una cuenta que solo tenga `audit.read`. | Puede consultar casos y aplicar filtros. El cambio de estado requiere el permiso adicional `crm.manage`. |

Registra el SHA, el rol usado y los pasos observados. Para otros casos, reutiliza un workspace descartable nuevo. Las [pruebas ASGI](../../../flowkron-operational-service/tests/test_privacy_cases.py) cubren aislamiento entre empresas, estados obsoletos, reintentos y ausencia de cambios en los registros sujetos a revisión.
