# KronFlow CRM (`frontend/app`)

SPA privada de **KronFlow — Intelligent CRM** (*By BLANDSKRON*) construida con **Angular 21.2** standalone en modo **100% Zoneless (`provideZonelessChangeDetection`) + `ChangeDetectionStrategy.OnPush`**, Design System Teal/Esmeralda/Cyan con tipografía `Sora` + `Inter` + `JetBrains Mono`, Floating Glassmorphism, temas claro/oscuro persistentes y accesibilidad WCAG 2.2 AA.

## Capacidades implementadas

- **Autenticación y acceso multi-tenant:** login por correo/contraseña, Google Identity Services, registro/confirmación de correo, recuperación de contraseña y onboarding obligatorio de empresa (`authGuard` / `noAuthGuard`).
- **Workspace y administración:** edición de empresa y logo, perfil y avatar, gestión de equipo, invitaciones, roles RBAC y notificaciones.
- **Bandeja HITL y conversaciones (`/app/conversations`):** búsqueda y segmentación de hilos, toma/liberación de control humano (`CAS`), compositor de respuestas y cambio entre atención humana e IA.
- **Directorio de contactos (`/app/contacts`) y leads (`/app/leads`):** alta idempotente, búsqueda por origen/texto, consentimiento, eventos de dominio y fichas detalladas.
- **Pipeline de oportunidades (`/app/opportunities` y `/app/workflows`):** etapas editables, creación reactiva tipada y control optimista de versión.
- **Contexto empresarial y simulador RAG (`/app/business-context`):** progreso real del agente, carga multipart de documentos, plantillas Word/PDF, asistente interactivo de setup y simulador RAG con inspección de fuentes y confianza.
- **Propuestas IA (`/app/ai-proposals`):** bandeja de aprobación, rechazo y ejecución `at-most-once` con previsualización de argumentos.
- **Campañas y analítica (`/app/campaigns`, `/app/analytics`):** conexiones de correo delegadas, plantillas, worker stub, métricas comerciales, temperatura de leads, actividad diaria e indicadores consolidados.
- **Privacidad y auditoría (`/app/settings/privacy`, `/app/settings/audit-events`):** solicitudes de exportación/supresión y feed histórico filtrado.
- **Canal WhatsApp (`/app/whatsapp`):** vinculación QR multi-tenant, transiciones de estado y desconexión segura.

El frontend nunca invoca rutas `/internal/*` ni envía `schema_name`. Para Contexto Empresarial y Simulación consume `agent-core`; para CRM, pipeline, campañas y analítica consume `operational-service`; para identidad y sesión consume `auth-service`.

## Desarrollo local

```sh
npm ci
npm start
```

Angular sirve en `http://localhost:4200`. Validación y build de producción:

```sh
npm run lint
npm test
npm run build
```

Salida de producción: `dist/app/browser` (presupuestos CSS por componente: `8 kB` warning / `12 kB` error).

## Docker

```sh
docker compose --env-file .env.local up --build
```

Nginx endurecido publica la SPA en `http://localhost:8081` con `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy` y cache inmutable para assets hasheados. Los literales de `src/environments/environment.ts` se inyectan en tiempo de build:

| Build arg | Default Docker | Uso |
| --- | --- | --- |
| `API_PUBLIC_URL` | `http://localhost:8000/api/v1` | API IAM / tenants |
| `OPERATIONAL_API_PUBLIC_URL` | `http://localhost:8001/api/v1` | API operacional |
| `AGENT_CORE_API_PUBLIC_URL` | `http://localhost:8002/api/v1` | Agent Core (contexto y RAG) |
| `LANDING_PUBLIC_URL` | `http://localhost:8080` | Retorno a portal público |
| `SALES_WHATSAPP_NUMBER` | `""` | Botón comercial opcional (oculto si está vacío) |

## Documentación

Consulta [docs/README.md](docs/README.md) para arquitectura, rutas, APIs, configuración, seguridad y pruebas. Las reglas para agentes de código viven en [AGENTS.md](AGENTS.md).
