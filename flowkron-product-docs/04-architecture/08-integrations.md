# Integraciones

Versión: 1.2
Tipo: estado actual
Estado: `PARTIAL`
Última verificación técnica: 2026-07-23

| Integración | Estado | Evidencia y límite |
| --- | --- | --- |
| App → Auth | `IMPLEMENTED` | Login, perfil, tenant, equipo y settings |
| App → Operational | `PARTIAL` | Leads, conversaciones y analytics; mensajes solo lectura |
| App → Agent Core | `PARTIAL` | Contexto, plantillas, carga, status, setup y simulación |
| Landing → Auth | `IMPLEMENTED` | CSRF y contacto público |
| Auth → Operational | `PARTIAL` | Provisión/runtime síncrono, con fallos `502` |
| Agent Core → Operational | `PARTIAL` | Documentos, status y retrieval interno |
| Operational ingest HTTP | `IMPLEMENTED` como API | Preparado para gateway con tenant code/key |
| Adaptador externo → Operational ingest | `PARTIAL` | Interfaz de ingesta disponible y adaptador externo requerido |
| Auth → gateway de correo → Resend | `IMPLEMENTED` | Requiere configurar la credencial y el remitente autorizado |
| SMTP | `PARTIAL` | Auth depende de configuración externa |
| Google OAuth | `PARTIAL` | Backend/UI disponibles, dependientes de configuración |
| Billing provider | `NOT_IMPLEMENTED` | Solo estado/activación manual |
| Observabilidad externa | `NOT_IMPLEMENTED` | Sin stack ni exportadores |

## Regla

La presencia de código, nodo o variable no prueba que una integración externa esté habilitada. Para declararla operativa se requieren credenciales sandbox/productivas gestionadas, configuración del proveedor, prueba E2E, monitoreo, límites, manejo de errores y owner.
