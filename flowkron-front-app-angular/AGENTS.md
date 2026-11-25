# AGENTS.md

Fuente única de contexto e instrucciones agenticas para `flowkron-front-app-angular` (CRM privado de **KronFlow — Intelligent CRM**). `CLAUDE.md` y `GEMINI.md` son adaptadores mínimos.

## Propósito y límites

SPA Angular 21 privada que consume `flowkron-auth-service`, `flowkron-operational-service` y `flowkron-agent-core`. No confundas UI con capacidad backend:

- No existe ruta `/app/agents`; las capacidades visibles de agente estan en `/app/business-context`.
- `/app/integrations` redirige a `/app/whatsapp`, donde se vincula y diagnostica la conexión.
- La Bandeja consulta conversaciones y mensajes y usa `crm.manage` para marcar lectura. El envío manual queda pendiente.
- `/app/contacts` consulta el directorio con búsqueda y paginación del servidor.
- Workflow transforma conversaciones/leads en columnas; no tiene CRUD de workflows.
- Notificaciones consulta handoffs de Operational y dirige a la Bandeja filtrada por pendientes.
- `/app/pricing` redirige a `/app/home`.
- Contexto Empresarial usa Agent Core para plantillas, documentos, setup chat, simulacion y reglas de correccion.
- Métodos de runtime/provisión/suscripción existen en `TenantService`, pero ninguna pantalla los invoca.
- `npm test` está declarado, pero no hay target `test`, runner ni specs Angular.

## Mapa técnico

| Ruta | Responsabilidad |
| --- | --- |
| `src/app/app.routes.ts` | Rutas lazy y guards |
| `src/app/core/interceptors/auth.interceptor.ts` | Correlation ID, bearer, tenant y retry 401 |
| `src/app/domains/auth/` | Identidad, tenant, onboarding, perfil, miembros e invitaciones |
| `src/app/domains/agents/` | Contexto Empresarial, Agent Core y configuracion de agente operacional |
| `src/app/domains/conversations/` | Bandeja, historial y marcas de lectura |
| `src/app/domains/contacts/` | Directorio de contactos en modo lectura |
| `src/app/domains/leads/` | Leads usados por workflows |
| `src/app/domains/analytics/` | Resumen operacional |
| `src/app/domains/dashboard/` | Shell, home, workflows, integraciones, pricing, settings y notificaciones |
| `src/app/shared/utils/token-storage.ts` | JWT/tenant en localStorage |
| `src/environments/environment.ts` | Configuración pública compilada |
| `tests/visual/` | Smoke Playwright externo a Angular |

## Invariantes

- Mantener standalone components, lazy loading, strict TypeScript/templates y separación `core/domains/shared`.
- Toda llamada a las APIs debe pasar por `HttpClient` y el interceptor.
- No presentar los guards como autorización: el backend debe validar JWT, tenant, roles y permisos.
- Conservar contratos y envelope reales; Auth y Operational responden `ApiResponse<T>`/`ApiError`, y los servicios Angular desempaquetan `data` para las pantallas.
- Cambios de endpoints, DTOs, headers, tokens o flujos requieren coordinación con los servicios backend.
- Reconocer el riesgo XSS de guardar access/refresh tokens en `localStorage`; no introducir HTML no confiable ni bypasses de sanitización.
- Preservar gating por `requires_paid_plan`, manejo 402/403/404 operacional y controles por permisos en settings.

## Seguridad de sesión

Claves reales: `flowkron.access_token`, `flowkron.refresh_token`, `flowkron.tenant_id` y `theme`. El interceptor adjunta `X-Correlation-ID` a toda petición; bearer y `X-Tenant-ID` solo a URLs que comienzan con las bases configuradas. Ante 401 intenta un refresh compartido y reintenta una vez.


## Autorización del agente

Permitido: leer código/docs; editar componentes, estilos, servicios y documentación; crear pruebas; ejecutar build y smoke local.


No leer/modificar `.env`, `node_modules/`, `dist/`, `.angular/`, resultados generados ni workflows sin autorización. No desplegar ni publicar.

## Validación proporcional

```powershell
npm run build
```

- Docs: enlaces, referencias, fences y `git diff --check`.
- UI/auth/API: build y smoke/validación manual según flujo.
- No ejecutar ni reportar `npm test` como válido hasta configurar target/runner/specs.
- Smoke: `docker compose --profile visual up --build --abort-on-container-exit`; requiere Docker y red para instalar Playwright.
- Los screenshots requieren revisión manual; no existe comparación automática.

## Documentos canónicos

- [Índice](docs/README.md)
- [Arquitectura y capacidades](docs/ARCHITECTURE.md)
- [Rutas y APIs](docs/ROUTES_AND_APIS.md)
- [Configuración y operación](docs/CONFIGURATION_AND_OPERATIONS.md)
- [Seguridad](docs/SECURITY.md)
- [Testing](docs/TESTING.md)

## Definición de terminado

El cambio respeta alcance y contratos, no expone secretos, compila, mantiene auth/tenant/gating, actualiza pruebas/documentación y declara cualquier validación no ejecutada.
