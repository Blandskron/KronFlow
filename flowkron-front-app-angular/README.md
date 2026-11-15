# flowkron-front-app-angular

SPA privada de Flowkron construida con Angular 21 standalone. Implementa autenticacion manual, administracion de tenant y consumo de Auth, Operational y Agent Core.

## Alcance real

- Autenticacion por email/password.
- Recuperacion de contrasena e invitaciones de tenant para usuarios creados manualmente.
- Sesion JWT y tenant activo persistidos en `localStorage`.
- Dashboard protegido con conversaciones, workflow derivado, analytics, pricing y settings.
- Administracion de perfil, empresa, logo/avatar, miembros e invitaciones.
- Creacion de agente contra la API operacional.
- Contexto Empresarial contra Agent Core: descarga plantillas Word/PDF, sube documentos, consulta status real y ejecuta simulador RAG.

Limitaciones actuales:

- No existe ruta `/app/agents`; las capacidades de agente visibles viven en `/app/business-context`.
- `/app/integrations` es placeholder.
- Conversaciones permite consultar conversaciones/mensajes, pero no enviar mensajes.
- Workflow es una vista derivada de conversaciones/leads; no administra workflows persistentes.
- Notificaciones usa una lista local vacia.
- Pricing es contenido estatico y deriva contratacion a WhatsApp; no activa suscripciones.
- No existe suite unitaria configurada. El smoke Playwright solo cubre login y guarda screenshots sin baselines.

## Desarrollo

```powershell
npm ci
npm start
```

Angular sirve en `http://localhost:4200`. Build de produccion:

```powershell
npm run build
```

Salida: `dist/flowkron-front-app-angular/browser`.

## Docker

```powershell
docker compose --env-file .env.local up --build
```

Nginx publica la SPA en `http://localhost:8081`. Los valores de environment se compilan en el bundle; no cambian en runtime.

## Configuracion

| Build arg | Default Docker | Uso |
| --- | --- | --- |
| `API_PUBLIC_URL` | `http://localhost:8000/api/v1` | API de auth/tenants |
| `OPERATIONAL_API_PUBLIC_URL` | `http://localhost:8001/api/v1` | API operacional |
| `AGENT_CORE_API_PUBLIC_URL` | `http://localhost:8002/api/v1` | Agent Core para contexto y simulacion |
| `LANDING_PUBLIC_URL` | `http://localhost:8080` | Enlaces de retorno |
| `SALES_WHATSAPP_NUMBER` | `521234567890` | CTA comercial de pricing |

Son datos publicos del frontend, nunca un mecanismo para secretos.

El frontend no consume endpoints internos de Operational ni envia `schema_name`. Para Contexto Empresarial siempre llama a Agent Core; Agent Core resuelve tenant autenticado y delega persistencia/RAG a Operational.

## Documentacion

Consulta [docs/README.md](docs/README.md) para arquitectura, rutas, contratos, configuracion, seguridad, operacion y pruebas. Las instrucciones para agentes estan en [AGENTS.md](AGENTS.md).
