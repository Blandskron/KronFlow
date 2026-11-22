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
| `/app/conversations` | Bandeja con búsqueda, historial y marca de lectura; `?status=waiting` abre las pendientes |
| `/app/contacts` | Directorio de lectura con búsqueda, origen y paginación del servidor. La URL conserva origen y página; el término de búsqueda queda en el historial de navegación de esa pestaña. |
| `/app/contacts/:id` | Ficha de lectura con retorno al directorio en el mismo contexto |
| `/app/workflows` | Tablero derivado de conversaciones y leads |
| `/app/whatsapp`, `/app/integrations` | Vinculación y diagnóstico de WhatsApp; `integrations` redirige a `whatsapp` |
| `/app/analytics` | Resumen operacional |
| `/app/notifications` | Lista de handoffs de la API con enlace a la Bandeja filtrada |
| `/app/pricing` | Redirige a `/app/home` |
| `/app/settings` | Perfil, empresa, miembros e invitaciones |

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
| GET | `/contacts` | Directorio de contactos (`users.read`) |
| GET | `/contacts/sources` | Sugerencias de origen en Contactos (`users.read`) |
| GET | `/contacts/{id}` | Ficha de contacto (`users.read`) |
| GET | `/leads` | Workflow |
| GET | `/analytics/summary` | Analytics |
| GET | `/agents` | Servicio disponible, sin pantalla actual |
| POST | `/agents/configure` | Stub de configuración; devuelve 501 |

Operational usa `ApiResponse<T>` para todas las respuestas JSON. El frontend privado no consume endpoints `/internal/*`.

## Agent Core

Base: `environment.agentCoreApiUrl`, sin slash final.

Contrato fuente: `../flowkron-api-contracts/openapi/services/agent-core.openapi.yml`.

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
