# Rutas y APIs

## Rutas

| Ruta | Proteccion | Componente/capacidad |
| --- | --- | --- |
| `/` | Ninguna | Redirige a `/login` |
| `/confirm-email` | Sin guard | Lee `token` desde query param y confirma correo |
| `/forgot-password`, `/reset-password` | Sin guard | Recuperacion |
| `/onboarding/company` | `authGuard` | Alta inicial de empresa cuando el usuario no tiene tenant |
| `/app/**` | `authGuard` + `canActivateChild` | Dashboard autenticado |
| `**` | Ninguna | Redirige a `/login` |

Rutas hijas reales bajo `/app`:

| Ruta | Estado |
| --- | --- |
| `/app` | Redirige a `/app/home` |
| `/app/home` | Resumen de sesion, tenant y plan |
| `/app/business-context` | Contexto Empresarial integrado con Agent Core |
| `/app/conversations` | Bandeja con búsqueda, historial, marca de lectura y barra HITL (`Reclamar`, `Responder`, `Devolver a IA`, `Resolver`); `?status=waiting` abre las pendientes |
| `/app/contacts` | Directorio de lectura con búsqueda, origen y paginación del servidor. La URL conserva origen y página; el término de búsqueda queda en el historial de navegación de esa pestaña. |
| `/app/contacts/new` | Alta manual con `crm.manage`, nombre obligatorio y puntos de contacto opcionales. El reintento reutiliza la solicitud. |
| `/app/contacts/:id` | Ficha con leads y conversaciones vinculadas, con reintentos por sección. Muestra el correo y teléfono normalizados cuando están disponibles y usa el valor original en los demás casos. `crm.manage` permite editar el nombre. Un conflicto ofrece recargar la ficha con el nombre vigente. |
| `/app/leads` | Seguimiento de leads de la empresa. La URL conserva `contact_id`, `status_group`, `temperature` y `offset`. El término de búsqueda se guarda en el historial de navegación de la pestaña. Se puede quitar el filtro de contacto desde la lista. |
| `/app/leads/:id` | Ficha con enlace al contacto, calificación por etapa y temperatura con `crm.manage`, e historial con `audit.read`. Se abre desde Contactos o Seguimiento. |
| `/app/workflows` | Tablero derivado de conversaciones y leads |
| `/app/opportunities` | Pipeline comercial (`FK-29`): alta de oportunidades, cambio de etapa con versión optimista y cierre ganada/perdida (`crm.manage`). |
| `/app/campaigns` | Campañas y conexiones delegadas (`FK-30`/`FK-24`): conexiones de correo, plantillas aprobadas, campañas con snapshot y despacho stub (`crm.manage`). |
| `/app/ai-proposals` | Bandeja de revisión de propuestas tipadas de IA (`FK-17`/`FK-18`): aprobar, rechazar y ejecutar efectos versionados (`crm.manage`). |
| `/app/whatsapp`, `/app/integrations` | Vinculación y diagnóstico de WhatsApp; `integrations` redirige a `whatsapp` |
| `/app/analytics` | Resumen operacional, tabla de actividad por intervalo/zona e indicadores consolidados (`/analytics/kpis`). |
| `/app/notifications` | Cola paginada de atención actual con enlaces a la Bandeja y vista `?view=history` para derivaciones registradas. |
| `/app/pricing` | Redirige a `/app/home` |
| `/app/settings` | Perfil, empresa, miembros e invitaciones |
| `/app/settings/privacy` | Bandeja de privacidad con `audit.read`. `crm.manage` habilita revisión, cierre, exportación JSON (`/export`), borrado/anonimización (`/erase`) y barrido de retención (`/retention/sweep`). |
| `/app/settings/audit-events` | Historial de auditoría con filtros por evento y UUID, paginación y enlaces al CRM. Requiere `audit.read`. |

No existe ruta `/app/agents` en el router actual.

El guard comprueba presencia de access token y, si falta usuario cargado, valida `/auth/me/`. Si el usuario autenticado no tiene tenant, bloquea `/app/**` y lo dirige a `/onboarding/company`. Si ya tiene tenant, bloquea volver al onboarding y dirige a `/app/home`. Es una barrera de navegacion, no autorizacion de seguridad.

## Auth y tenants

Base: `environment.apiUrl`, sin slash final.

- Perfil: patch y avatar multipart.
- Confirmacion de email: `POST /auth/email/confirm/` con token recibido en `/confirm-email?token=...`.
- Onboarding de empresa: `POST /tenants/onboarding/` crea el tenant inicial, asigna owner y renueva tokens con tenant.
- Tenant: patch, logo, miembros, invitaciones, runtime/provision y activacion de suscripcion.

Las respuestas de auth/tenant usan `ApiResponse<T> { success, status, data, meta }`. Los errores usan `ApiError` problem-details con `error_code`, `detail`, `errors` y `meta`.

## Operational

Base: `environment.operationalApiUrl`, sin slash final.

| Metodo | Endpoint | Uso visible |
| --- | --- | --- |
| GET | `/conversations` | Chats y workflow |
| GET | `/conversations/{id}/messages` | Detalle de chat |
| GET | `/conversations/handoff-history` | Derivaciones históricas con enlaces a destinos vigentes (`users.read`) |
| GET | `/contacts` | Directorio de contactos (`users.read`) |
| GET | `/contacts/sources` | Sugerencias de origen en Contactos (`users.read`) |
| GET | `/contacts/{id}` | Ficha de contacto (`users.read`) |
| GET | `/contacts/{id}/whatsapp-consent` | Estado e historial de consentimiento de WhatsApp desde la ficha (`audit.read`) |
| POST | `/contacts` | Alta manual con reintento por UUID (`crm.manage`) |
| PATCH | `/contacts/{id}/points` | Actualizar o borrar correo y teléfono de contactos manuales con precondición (`crm.manage`) |
| PATCH | `/contacts/{id}` | Editar nombre con comprobación de valor esperado (`crm.manage`) |
| POST | `/contacts/{id}/lead` | Iniciar seguimiento y abrir el lead existente o recién creado (`crm.manage`) |
| GET | `/leads` | Workflow, actividad del contacto y seguimiento paginado |
| GET | `/leads/{id}` | Ficha y contacto vinculado (`users.read`) |
| PATCH | `/leads/{id}` | Guardar etapa y temperatura con comprobación de `updated_at` (`crm.manage`) |
| GET | `/leads/{id}/activity` | Historial de alta y cambios de etapa o temperatura (`audit.read`) |
| GET | `/analytics/summary` | Analytics |
| GET | `/analytics/activity` | Actividad diaria y totales por fecha y zona (`users.read`) |
| GET | `/analytics/kpis` | Indicadores consolidados de pipeline, campañas, eventos y gobernanza (`users.read`) |
| GET/POST | `/conversations/{id}/control`, `/claim`, `/messages`, `/return-to-ai`, `/resolve` | Control HITL de conversación y respuesta humana en outbox (`crm.manage`) |
| GET/POST/PATCH | `/opportunities/stages`, `/opportunities`, `/opportunities/{id}` | Pipeline comercial con versión optimista y cierre `won`/`lost` (`crm.manage`) |
| GET/POST | `/ai-proposals`, `/ai-proposals/{id}/approve`, `/reject`, `/execute` | Revisión y ejecución `at-most-once` de propuestas IA (`crm.manage`) |
| GET/POST | `/channels/connections`, `/templates`, `/campaigns`, `/campaigns/{id}/approve`, `/campaigns/dispatch-stub` | Conexiones delegadas de correo y campañas con worker stub (`crm.manage`) |
| GET | `/operational/privacy-cases` | Seguimiento de solicitudes (`audit.read`) |
| GET | `/operational/audit-events` | Consulta histórica filtrada por tipo y correlación (`audit.read`) |
| PATCH | `/operational/privacy-cases/{id}` | Registrar transición confirmada (`audit.read` y `crm.manage`) |
| POST | `/operational/privacy-cases/{id}/export`, `/erase`, `/operational/retention/sweep` | Exportación JSON, anonimización/supresión y barrido de retención (`audit.read` y `crm.manage`) |
| GET | `/agents` | Servicio disponible, sin pantalla actual |
| POST | `/agents/configure` | Stub de configuración; devuelve 501 |

Operational usa `ApiResponse<T>` para todas las respuestas JSON. El frontend privado no consume endpoints `/internal/*`.

Tras un conflicto de etapa, el seguimiento consulta la lista con los filtros vigentes y muestra el estado devuelto por el servidor. El operador puede elegir una etapa y confirmar otro intento. Si el cambio deja la página fuera del rango de resultados, la lista vuelve a la última página válida.

## Agent Core

Base: `environment.agentCoreApiUrl`, sin slash final.

Contrato runtime: `/openapi.json` en `agent-core` y reglas en `ARCHITECTURE.md`.

| Metodo | Endpoint | Uso |
| --- | --- | --- |
| POST | `/agent/messages` | Endpoint universal para gateways/adaptadores |
| POST | `/agent/simulate` | Simulador interno de agente |
| GET | `/context/status` | Estado real de progreso, agente, documentos activos y acciones permitidas |
| GET | `/context/documents` | Listar documentos de contexto empresarial cargados |
| POST | `/context/documents/upload-file` | Carga multipart de archivos completados; Agent Core extrae texto |
| POST | `/context/documents/upload` | Carga JSON de texto ya extraido; uso tecnico |
| PATCH/DELETE | `/context/documents/{id}` | Publicar borradores/eliminar segun `document_actions` de `context/status` |
| GET | `/context/templates` | Obtener catalogo de plantillas disponibles con opciones Word/PDF |
| GET | `/context/templates/{id}/download` | Descargar una plantilla individual en Word o PDF |
| POST | `/setup-chat/sessions` | Iniciar chat interactivo de onboarding IA |
| POST | `/setup-chat/sessions/{id}/messages` | Conversar con el asistente de onboarding IA |
| POST | `/setup-chat/sessions/{id}/generate-context` | Generar contexto estructurado a partir del chat |
| POST | `/agent/rules` | Crear correcciones desde el simulador |
| GET/PATCH/DELETE | `/agent/rules` | Metodos disponibles en data access; sin pantalla dedicada actual |
| GET | `/agent/conversations/{id}/traces`, `/agent/traces/{id}` | Metodos disponibles en data access; sin pantalla dedicada actual |

El frontend no debe enviar `schema_name`. Agent Core opera con tenant autenticado y Operational resuelve schema fisico/industria.

La seccion Contexto Empresarial debe mostrar exactamente lo que devuelve Agent Core. Si `GET /context/status` reporta cero documentos, la tabla debe aparecer vacia aunque el usuario haya cargado documentos en un contenedor viejo o entorno distinto.

## Interceptor

Para cada request genera `X-Correlation-ID` con `crypto.randomUUID()`. Solo cuando la URL comienza con una de las bases configuradas:

- agrega `Authorization: Bearer <access>` y `X-Tenant-ID` si existen;
- ante 401 protegido, comparte una unica peticion de refresh concurrente y reintenta una vez;
- si refresh falla, limpia sesion y navega a login;
- si el retry falla contra auth, limpia sesion; un fallo de retry operational/agent-core no borra la sesion auth.

Los permisos (`tenants.manage`, `members.manage`) controlan acciones de settings en UI, pero el backend debe volver a autorizarlas.
