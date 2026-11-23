# Arquitectura y capacidades

## Aplicacion

SPA CSR Angular 21 **Zoneless** (`provideZonelessChangeDetection()`, sin `zone.js`) con `bootstrapApplication`, 100% componentes standalone + `ChangeDetectionStrategy.OnPush`, routing lazy, Signals y Reactive Forms tipados. `app.config.ts` registra Zoneless, router (`withComponentInputBinding()`) y `HttpClient` con `authInterceptor`. No hay SSR, hydration, `@angular/animations` ni state manager externo.

```text
Browser -> Angular Router -> auth/onboarding/dashboard
                       -> Auth API (identidad, tenant, perfil)
                       -> Operational API (conversaciones, leads, analytics, agentes)
                       -> Agent Core API (contexto, simulacion, reglas, trazas)
```

`AuthService` es la fuente principal de usuario, tenant, roles, permisos y suscripcion. `WorkspaceStateService` adapta parte de ese estado y conserva agentes/empresa solo en memoria cuando no provienen del backend. `ThemeService` persiste claro/oscuro.

## Estado funcional de pantallas

| Area | Estado actual |
| --- | --- |
| Verificacion/reset/invitacion | Integrado con Auth API |
| Crear agente | Llama `POST /agents/configure` y valida el tenant code mostrado por auth |
| Home | Resumen de sesion/tenant y gating de plan |
| Contexto Empresarial | Integrado con Agent Core: carga documentos, descarga plantillas Word/PDF, consulta status real y simula/probar respuestas del agente |
| Conversaciones | Lista y detalle de mensajes, solo lectura |
| Workflows | Tablero derivado de conversaciones + leads; no persiste cambios |
| Integraciones | Placeholder |
| Analytics | Consume resumen operacional; actividad reciente queda vacia |
| Notificaciones | Lista local vacia; sin API |
| Pricing | Catalogo estatico USD/MXN y contratacion por WhatsApp |
| Settings | Perfil, avatar, tenant, logo, miembros, roles e invitaciones segun permisos |

No hay ruta `/app/agents` en el router actual. El dominio `agents` del codigo contiene data access y UI para `/app/business-context`, ademas del servicio que configura un agente contra Operational durante onboarding.

## Contexto Empresarial

La pantalla no contiene mocks de documentos ni calcula progreso localmente. El flujo esperado es:

1. `GET /context/templates` en Agent Core lista las cinco plantillas base y opciones de descarga Word/PDF.
2. El usuario descarga una plantilla, la completa y la sube por `POST /context/documents/upload-file`.
3. Agent Core extrae texto y delega persistencia/chunks a Operational.
4. `GET /context/status` devuelve progreso, documentos activos, fecha de ultima actualizacion y acciones permitidas.
5. El setup chat usa `/setup-chat/sessions`, `/setup-chat/sessions/{id}/messages` y `/setup-chat/sessions/{id}/generate-context`.
6. `POST /agent/simulate` devuelve respuesta, confianza, accion y fuentes consultadas.
7. Las correcciones del simulador crean reglas con `POST /agent/rules`.

El front no llama `/internal/*`, no conoce `tenant_blandskron` y no debe enviar `schema_name`. El tenant llega por JWT/header gestionado por el interceptor.

## Estado y persistencia

| Clave | Contenido |
| --- | --- |
| `flowkron.access_token` | JWT access |
| `flowkron.refresh_token` | JWT refresh |
| `flowkron.tenant_id` | ID numerico del tenant activo |
| `theme` | `light` o `dark` |


## Dependencias externas

- Auth API y Operational API.
- Agent Core API para capacidades conversacionales omnicanal.
- WhatsApp mediante `wa.me` en pricing.
- Lucide Angular para iconos.

## Diseno y accesibilidad

La UI usa un Design System en capas (`src/styles/tokens.css`, `reset.css`, `primitives.css`) sincronizado con `flowkron-front-landing-angular`, tipografía `Manrope` cargada vía `<link rel="preconnect">`, primitivos atómicos `OnPush` en `src/app/shared/ui/` (`flowkron-page-header`, `flowkron-stat-card`, `flowkron-badge`, `flowkron-alert`, `flowkron-empty-state`, `flowkron-dialog`, `flowkron-tabs`, `flowkron-skeleton`, `flowkron-toast-container`) y tema claro/oscuro gestionado por `ThemeService` (con sincronización de `meta[name="theme-color"]`). Las plantillas están cubiertas por `@angular-eslint/template/accessibility` (`0 errors, 0 warnings`).
