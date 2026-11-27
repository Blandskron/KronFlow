# AGENTS.md — Protocolo Agents-First, Human-Friendly (KronFlow)

Fuente única de contexto, reglas operativas y validación para agentes de IA y desarrolladores humanos en **KronFlow — Intelligent CRM** (*By BLANDSKRON*, Apache-2.0, `tenant_schema_v22`).

> **Regla de oro:** El código ejecutable, los esquemas OpenAPI/SQLAlchemy/Django y `.github/workflows/validate.yml` prevalecen siempre sobre cualquier resumen textual. No asumas capacidades no verificadas en el código.

---

## 1. Mapa del monorepo y documentación canónica

Cada microservicio backend, cada frontend y el stack de despliegue mantienen **un único `README.md` canónico**. La documentación transversal vive únicamente en la raíz.

| Dominio | Ruta | Stack | Puerto local | Documentación |
| --- | --- | --- | --- | --- |
| Raíz / Arquitectura | `/` | Monorepo | — | [README.md](README.md) · [ARCHITECTURE.md](ARCHITECTURE.md) · [RELEASE_READINESS.md](RELEASE_READINESS.md) |
| IAM & Tenants | `backend/auth-service` | Django 5 / DRF / PG / Redis | `8000` | [backend/auth-service/README.md](backend/auth-service/README.md) |
| CRM & Operaciones | `backend/operational-service` | FastAPI / PG 18 (`tenant_schema_v22`) + Worker | `8001` | [backend/operational-service/README.md](backend/operational-service/README.md) |
| Runtime IA & RAG | `backend/agent-core` | FastAPI / RAG / Groq opcional | `8002` | [backend/agent-core/README.md](backend/agent-core/README.md) |
| Correo transaccional | `backend/mail-service` | FastAPI / Redis / Resend HTTPS | `8000` (interno) | [backend/mail-service/README.md](backend/mail-service/README.md) |
| WhatsApp Lab | `backend/baileys-services` | Node 24 / TypeScript / Baileys | `3001` (interno) | [backend/baileys-services/README.md](backend/baileys-services/README.md) |
| CRM Web App | `frontend/app` | Angular 21.2 Zoneless (`OnPush`) | `8081` (`4200` dev) | [frontend/app/README.md](frontend/app/README.md) |
| Landing Pública | `frontend/landing` | Angular 21.2 Zoneless (`OnPush`) | `8080` (`4200` dev) | [frontend/landing/README.md](frontend/landing/README.md) |
| Despliegue local | `deploy/` | Docker Compose modular + smoke E2E | — | [deploy/README.md](deploy/README.md) |

---

## 2. Invariantes críticas (no romper)

1. **Aislamiento multi-tenant (`schema_translate_map`):**
   - Nunca aceptar `schema_name` desde requests públicos o del frontend; `operational-service` resuelve el schema desde el JWT validado y `TenantRuntime` activo.
   - Nunca interpolar identificadores SQL sin `sanitize_schema_name` y quoting seguro.
   - Toda mutación sobre modelos tenant debe mantener migraciones repetibles `v3–v22` (o incrementar `TENANT_MIGRATION_VERSION` con prueba en `test_tenant_upgrade_matrix.py`).
2. **Tres fronteras estrictas de autenticación:**
   - **Browser → APIs:** `Authorization: Bearer <JWT RS256>` (nunca aceptar refresh tokens como access tokens).
   - **Ingesta de canales → Operational:** `X-Tenant-Code` + `X-Ingest-Key` (o firma HMAC-SHA256 verificada por ruta de webhook).
   - **Servicio a servicio (`/internal/*`):** `X-Internal-Token` compartido; jamás expuesto a clientes públicos ni invocado desde Angular.
3. **Compatibilidad criptográfica y de sesión:**
   - Preservar defaults `JWT_ISSUER=flowkron-auth-service`, `JWT_AUDIENCE=flowkron`, `SIGNING_KEY_ENCRYPTION_SALT=flowkron-auth-service`, montajes `/run/flowkron` y claves `localStorage` (`flowkron.access_token`, `flowkron.refresh_token`, `flowkron.tenant_id`, `theme`).
4. **Efectos durables y gobernanza HITL:**
   - Envíos salientes, campañas, webhooks y notificaciones pasan por `action_outbox_jobs` y el worker durable (`worker.py` + `outbox_dispatcher.py`).
   - Propuestas IA se ejecutan `at-most-once`; la toma humana (`CAS`) y las bajas (`consent_ledger` / `contact_suppressions`) bloquean salidas automáticas.
5. **Frontend Angular 21 Zoneless:**
   - Mantener componentes standalone, `ChangeDetectionStrategy.OnPush`, lazy loading, tipado estricto y paso obligatorio por `HttpClient` + `auth.interceptor.ts`.
   - Los guards de Angular son UX, nunca seguridad: la autorización real siempre reside en backend.
6. **Cero secretos en Git:**
   - Nunca leer, imprimir ni versionar `.env`, claves privadas PEM, tokens reales o sesiones de WhatsApp.
   - Los valores sintéticos en tests no deben parecer secretos reales de alta entropía; toda la historia pasa por `gitleaks` en CI.

---

## 3. Catálogo de Skills (`.agents/skills/`)

Carga la skill correspondiente antes de editar cada dominio:

| Skill | Ruta | Cuándo usarla |
| --- | --- | --- |
| `ui-ux-pro-max` | [.agents/skills/ui-ux-pro-max/SKILL.md](.agents/skills/ui-ux-pro-max/SKILL.md) | Diseño visual, Design System, accesibilidad WCAG 2.2 AA, layout y componentes UI |
| `backend-multitenant` | [.agents/skills/backend-multitenant/SKILL.md](.agents/skills/backend-multitenant/SKILL.md) | Cambios en `operational-service`, `auth-service`, `agent-core`, `mail-service`, schemas y migraciones |
| `angular-frontend` | [.agents/skills/angular-frontend/SKILL.md](.agents/skills/angular-frontend/SKILL.md) | Cambios en `frontend/app` o `frontend/landing`, rutas, servicios HTTP, Vitest y ESLint |
| `compose-deploy-and-ci` | [.agents/skills/compose-deploy-and-ci/SKILL.md](.agents/skills/compose-deploy-and-ci/SKILL.md) | Cambios en `deploy/`, `compose*.yaml`, smoke tests, CI (`validate.yml`) y `gitleaks` |
| `docs-and-agents-protocol` | [.agents/skills/docs-and-agents-protocol/SKILL.md](.agents/skills/docs-and-agents-protocol/SKILL.md) | Actualizar `README.md`, `ARCHITECTURE.md`, `AGENTS.md` o skills manteniendo estructura minimalista |
| `blandskron-git-flow` | [.agents/skills/blandskron-git-flow/SKILL.md](.agents/skills/blandskron-git-flow/SKILL.md) | Gobernanza Git (`BLK-ENG-001` Perfil A): ramas, Conventional Commits, PRs, releases SemVer, hotfix/rollback e higiene |

---

## 4. Autorización del agente

- **Permitido directamente:** leer código y docs, editar código/pruebas/docs dentro del alcance pedido, ejecutar linters, tests unitarios/integración en bases descartables, builds y `docker compose ... config --quiet`.
- **Requiere aprobación explícita:** cambios destructivos en bases compartidas/productivas, `docker compose down -v`, rotación/borrado de claves reales, despliegues a producción o cambios incompatibles de contrato público.
- **Prohibido:** leer o exponer `.env`, claves privadas (`jwt_private.pem`), credenciales reales, o deshabilitar checks de seguridad/CI para evadir fallos.

---

## 5. Validación proporcional (paridad con CI)

Ejecuta solo las comprobaciones aplicables al alcance modificado y reporta explícitamente qué corrió y qué no:

| Área modificada | Comando de verificación |
| --- | --- |
| `backend/auth-service` | `ruff check --select E9,F63,F7,F82 .` · `python manage.py check` · `python manage.py test` |
| `backend/operational-service` | `ruff check --select E9,F63,F7,F82 .` · `python -m unittest discover -s tests -v` · `python -c "from app.main import app; assert app.openapi()['paths']"` |
| `backend/agent-core` | `ruff check --select E9,F63,F7,F82 .` · `python -m pytest -q` |
| `backend/mail-service` | `ruff check --select E9,F63,F7,F82 .` · `python -m pytest -q` |
| `backend/baileys-services` | `npm test` |
| `frontend/app` / `frontend/landing` | `npm run lint` · `npm test` · `npm run build` |
| `deploy/` o `compose*.yaml` | `docker compose --env-file .env.example config --quiet` · `docker compose -f compose.demo.yaml --env-file .env.example config --quiet` |
| Secretos / historia Git | `docker run --rm -v "${PWD}:/repo" zricethezav/gitleaks:v8.30.1 git --redact=100 --no-banner --log-opts='--all' /repo` |

---

## 6. Política de documentación y Definición de Terminado

- **Sin proliferación documental:** no crear carpetas `docs/*.md` por servicio ni duplicar `AGENTS.md` en subdirectorios. Todo documento de servicio vive en su `README.md`; los flujos repetibles viven en `.agents/skills/`.
- **Terminado significa:** diff acotado al alcance, invariantes multi-tenant y de seguridad intactas, cero enlaces rotos, cero secretos expuestos, validaciones relevantes ejecutadas y reportadas con honestidad.
