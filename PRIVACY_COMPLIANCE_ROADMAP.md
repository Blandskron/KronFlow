# Roadmap de Privacidad y Cumplimiento por Ciclos — KronFlow

**Documento base:** [PRIVACY_COMPLIANCE_AUDIT.md](PRIVACY_COMPLIANCE_AUDIT.md) (`tenant_schema_v21`, corte `169db37`, 26 nov 2026)  
**Propósito:** Plan incremental, priorizado y directamente ejecutable por otro agente de ingeniería (ciclo por ciclo), con backlog trazable, estrategia de pruebas y **Quality Gates bloqueantes** al cierre de cada ciclo.

---

## 1. Visión General de Ciclos (0 a 9)

| Ciclo | Foco principal | Brechas cubiertas | Quality Gate bloqueante |
| --- | --- | --- | --- |
| **Ciclo 0** | Diagnóstico, inventario declarativo PII y alcance normativo | GAP-01 | `QG-0`: Inventario YAML cubre 100% de tablas/columnas PII en CI |
| **Ciclo 1** | Riesgos críticos y fugas activas (`/erase`, egreso LLM, retención básica) | GAP-05, GAP-14, GAP-16 | `QG-1`: Cero PII residual tras `/erase` y bloqueo de egreso LLM sin opt-in + scrubber |
| **Ciclo 2** | Fundamentos arquitectónicos y seguridad (CSP/HSTS, revocación JWT, cifrado PII) | GAP-07, GAP-08, GAP-09 | `QG-2`: Headers CSP/HSTS activos, revocación <5s vía Redis y cifrado de secretos/RUT |
| **Ciclo 3** | Licitud, consentimiento interoperable (`TS 27560`) y transparencia (`ISO 29184` / Art. 50) | GAP-02, GAP-03, GAP-04 | `QG-3`: `rut` opcional, recibos `TS 27560`, aviso IA Art. 50 y política configurable |
| **Ciclo 4** | Derechos completos de titulares (ARCOP+B) en Operational e IAM | GAP-05, GAP-06, GAP-17 | `QG-4`: Exportación portable completa, rectificación, bloqueo y DSAR IAM operativos |
| **Ciclo 5** | Ciclo de vida automatizado (retención multi-tabla, baja de tenant, *tombstones*) | GAP-06, GAP-10, GAP-11 | `QG-5`: Purga automática en `worker.py` + `auth-service` y reaplicación post-restore |
| **Ciclo 6** | Proveedores, integraciones, MCP remoto, menores y datos sensibles | GAP-14, GAP-15, GAP-16 | `QG-6`: Registro de subencargados por tenant, opt-in obligatorio y filtro de datos sensibles |
| **Ciclo 7** | Gobernanza, auditoría inmutable, DPIA e incidentes (SLA 3h/72h) | GAP-12, GAP-13, GAP-18 | `QG-7`: Auditoría con hash chain, módulo/runbook de incidentes y plantilla DPIA ISO 29134 |
| **Ciclo 8** | Automatización del cumplimiento (*Compliance as Code*) en CI | GAP-01, GAP-18 | `QG-8`: Jobs de privacidad, paridad de inventario y auditoría integrados en `validate.yml` |
| **Ciclo 9** | Validación integral, ensayo de restore FK-15 y preparación para producción | Todos + gates externos | `QG-9`: Suite E2E completa, restore con *tombstones*, revisión jurídica y *Go/No-Go* |

---

## 2. Backlog de Tareas Ejecutables por Ciclo

> **Convenciones:** Prioridad (`P0` Crítica, `P1` Alta, `P2` Media) · Complejidad (`S` ≤1 día, `M` 2–3 días, `L` 4–5 días). Todas las migraciones de `operational-service` deben ser aditivas, idempotentes y probadas en `test_tenant_upgrade_matrix.py`.

### Ciclo 0 — Diagnóstico, Inventario y Alcance Normativo
- **`PRV-001` · Manifiesto declarativo de inventario PII (`compliance/data_inventory.yaml`)**
  - **Objetivo:** Inventariar 100% de tablas/columnas con PII y datos sensibles en `auth-service` y `operational-service`.
  - **Alcance / Componentes:** `compliance/data_inventory.yaml`, `backend/operational-service/tests/test_pii_inventory_parity.py`, `backend/auth-service/apps/audit/tests.py`.
  - **Normativa:** GDPR Art. 30 · Ley 21.719 Art. 14 quater · ISO/IEC 27701:2025.
  - **Dependencias:** Ninguna · **Prioridad:** P1 · **Complejidad:** M.
  - **Criterios de aceptación:** Cada columna PII declara categoría, sensibilidad, base legal, retención y acción en `/export` y `/erase`; el test falla ante tablas/columnas nuevas sin declarar.
  - **Pruebas / DoD:** `unittest` + Django `test` verdes; 0 columnas PII sin clasificar.
- **`PRV-002` · Matriz de roles y jurisdicciones por despliegue (`tenant_privacy_profile`)**
  - **Objetivo:** Permitir configurar por instancia/tenant jurisdicción aplicable (`CL`, `EU`, `LATAM`), contacto DPO y URL de política legal.
  - **Alcance / Componentes:** `backend/auth-service/apps/tenants/models.py`, API tenant settings, `frontend/app` settings.
  - **Normativa:** GDPR Art. 13, 37 · Ley 21.719 Art. 14 ter · ISO 29100:2024.
  - **Dependencias:** `PRV-001` · **Prioridad:** P1 · **Complejidad:** S.
  - **Criterios de aceptación:** Campos `privacy_jurisdiction`, `dpo_contact_email`, `privacy_policy_url` editables por `TENANT_OWNER` y expuestos en avisos públicos.
  - **Pruebas / DoD:** Migración Django + test RBAC (solo owner/admin edita).

> **Quality Gate `QG-0`:** `test_pii_inventory_parity.py` pasa al 100% y el manifiesto cubre todos los modelos activos (`tenant_schema_v21` + IAM).

---

### Ciclo 1 — Riesgos Críticos y Fugas Activas (P0)
- **`PRV-003` · Remediación completa de `/erase` (eliminación de fuga de RUT y PII residual)**
  - **Objetivo:** Cerrar todas las fugas residuales detectadas en `execute_privacy_erasure`.
  - **Alcance / Componentes:** `backend/operational-service/app/services/privacy_case_service.py`.
  - **Normativa:** GDPR Art. 17 · Ley 21.719 Art. 7 · ISO/IEC 29151:2026.
  - **Dependencias:** `PRV-001` · **Prioridad:** **P0** · **Complejidad:** M.
  - **Criterios de aceptación:** Anonimiza `clientes.rut` (`anon-<sha256-prefix>`), redacta `conversaciones.message`, `conversaciones_resumen`, `leads.resumen_ia`, `opportunity_activities.note`, `ai_action_proposals.arguments_json`/`rationale`, `domain_events.payload`, `external_entity_mappings` y `solicitudes_derechos.notas`; captura y registra supresión tanto para `email` como para `whatsapp` **antes** de anular `client.email`.
  - **Pruebas / DoD:** Test negativo busca `rut`, `email`, `telefono` y texto de mensaje en todas las tablas del schema tenant y exige `0` coincidencias.
- **`PRV-004` · Gate *Privacy by Default* para egreso a LLM externo y MCP remoto**
  - **Objetivo:** Impedir transferencias internacionales implícitas hacia Groq o servidores MCP sin autorización explícita del tenant.
  - **Alcance / Componentes:** `backend/operational-service/app/tenant_models/conversation_control.py` (`tenant_ai_policies`), `backend/agent-core/app/application/orchestration/agent_runtime.py`, `backend/operational-service/app/services/mcp_client_service.py`.
  - **Normativa:** GDPR Art. 25, 44–49 · Ley 21.719 Art. 27 · ISO/IEC 31700-1:2023.
  - **Dependencias:** Ninguna · **Prioridad:** **P0** · **Complejidad:** M.
  - **Criterios de aceptación:** `allow_external_ai_transfer` y `memory_auto_capture` inician en `False` por defecto; si es `False`, `agent-core` opera en modo local y rechaza egreso a Groq/MCP remoto con trazabilidad auditable.
  - **Pruebas / DoD:** Tests en `agent-core` y `operational-service` comprueban bloqueo por defecto y habilitación explícita con auditoría.
- **`PRV-005` · Filtro *PII Scrubber* pre-egreso hacia LLM y conectores IA**
  - **Objetivo:** Redactar/seudonimizar automáticamente RUT, emails, teléfonos y números de tarjeta antes de enviar prompts o memoria a `GroqClient` y `RemoteMCPServer`.
  - **Alcance / Componentes:** `backend/agent-core/app/infrastructure/llm/pii_scrubber.py` (nuevo), `groq.py`, `agent_runtime.py`, `mcp_client_service.py`.
  - **Normativa:** GDPR Art. 5.1.c, 25 · NIST Privacy Framework 1.1 §1.2.2 · ISO/IEC 29151:2026.
  - **Dependencias:** `PRV-004` · **Prioridad:** **P0** · **Complejidad:** M.
  - **Criterios de aceptación:** Ningún RUT chileno válido, email, teléfono `+56`/`E.164` ni PAN (Luhn) aparece en el payload JSON enviado a `api.groq.com`; placeholders reversibles solo en memoria local si se requiere.
  - **Pruebas / DoD:** Suite unitaria con fixtures sintéticos de PII chilena e internacional; verificación de payload HTTP mockeado.

> **Quality Gate `QG-1`:** Cero PII residual verificada tras `/erase` en todas las tablas tenant; `agent-core` bloquea egreso externo por defecto y el *PII Scrubber* pasa 100% de pruebas negativas.

---

### Ciclo 2 — Fundamentos Arquitectónicos y Seguridad
- **`PRV-006` · Cabeceras CSP estricta y HSTS en Nginx de ambos frontends**
  - **Objetivo:** Mitigar XSS y robo de tokens en navegador.
  - **Alcance / Componentes:** `frontend/app/nginx.conf`, `frontend/landing/nginx.conf`.
  - **Normativa:** GDPR Art. 32 · ISO/IEC 27001:2022 A.8.20/A.8.26 · OWASP ASVS.
  - **Dependencias:** Ninguna · **Prioridad:** P1 · **Complejidad:** S.
  - **Criterios de aceptación:** `Content-Security-Policy` sin `unsafe-eval`, orígenes restringidos a APIs configuradas, y `Strict-Transport-Security` listo para perfil HTTPS.
  - **Pruebas / DoD:** Smoke test verifica presencia de cabeceras y funcionamiento sin errores de consola en SPA.
- **`PRV-007` · Revocación rápida de JWT vía Redis compartido**
  - **Objetivo:** Eliminar la ventana de validez local de access tokens tras logout, cambio de rol o suspensión de usuario/tenant.
  - **Alcance / Componentes:** `backend/auth-service/apps/sessions/`, `backend/operational-service/app/core/security.py`, `backend/agent-core/app/core/tenant.py`.
  - **Normativa:** GDPR Art. 32 · ISO/IEC 27001:2022 A.5.17/A.8.5.
  - **Dependencias:** Ninguna · **Prioridad:** P1 · **Complejidad:** M.
  - **Criterios de aceptación:** Al revocar sesión o suspender usuario/tenant en IAM, se escribe `jti`/epoch en Redis; Operational y Agent Core rechazan el token con `401` en <5 segundos.
  - **Pruebas / DoD:** Test de integración verifica rechazo inmediato tras logout/suspensión; fallback seguro si Redis no responde.
- **`PRV-008` · Cifrado a nivel de aplicación (*Envelope Encryption*) para RUT y secretos de conectores**
  - **Objetivo:** Proteger identificadores críticos y tokens de terceros ante fuga de base de datos o backup.
  - **Alcance / Componentes:** `backend/operational-service/app/core/crypto.py` (nuevo), `clientes` (`rut_encrypted` + `rut_blind_index`), `tenant_channel_connections`, `remote_mcp_servers`.
  - **Normativa:** GDPR Art. 32.1.a · Ley 21.719 Art. 14 quinquies · ISO/IEC 27001 A.8.24 · ISO 29151:2026.
  - **Dependencias:** `PRV-001` · **Prioridad:** P2 · **Complejidad:** L.
  - **Criterios de aceptación:** Cifrado autenticado AES-GCM / Fernet con clave separada de DB y soporte de rotación; búsqueda exacta mediante blind index HMAC-SHA256.
  - **Pruebas / DoD:** Tests de cifrado, búsqueda por blind index, rotación de llave y migración repetible en `test_tenant_upgrade_matrix.py`.
- **`PRV-009` · Defensa en profundidad en tablas `public` y plan de cookies `HttpOnly`**
  - **Objetivo:** Auditar aislamiento por `auth_tenant_id` en tablas `public` (`webchat_widgets`, `channel_webhook_routes`, `capture_access`) y documentar/preparar migración de refresh token a cookie `HttpOnly; Secure; SameSite=Lax`.
  - **Alcance / Componentes:** `backend/operational-service/tests/`, `backend/auth-service/apps/accounts/views.py`, `frontend/app/src/app/core/interceptors/auth.interceptor.ts`.
  - **Normativa:** GDPR Art. 25, 32 · ISO/IEC 27001 A.8.3.
  - **Dependencias:** `PRV-006`, `PRV-007` · **Prioridad:** P2 · **Complejidad:** L.
  - **Criterios de aceptación:** Tests cross-tenant en todas las tablas `public`; refresh token opcionalmente gestionado por cookie `HttpOnly` con CSRF.
  - **Pruebas / DoD:** Suite auth + Vitest + smoke E2E verdes.

> **Quality Gate `QG-2`:** CSP/HSTS verificados, revocación JWT en <5s probada y 0 fallos cross-tenant o de cifrado.

---

### Ciclo 3 — Licitud, Consentimiento y Transparencia
- **`PRV-010` · Minimización de datos: hacer `clientes.rut` opcional y registrar `legal_basis`**
  - **Objetivo:** Eliminar la recolección obligatoria de RUT en canales donde no es estrictamente necesario y registrar base de licitud explícita.
  - **Alcance / Componentes:** `tenant_schema_v22` (`clientes.rut` nullable, `contact_consent_decisions.legal_basis`, `notice_version`, `notice_hash`), `contacts.py`, `capture_service.py`, `frontend/app`.
  - **Normativa:** GDPR Art. 5.1.c, 6 · Ley 21.719 Art. 3, 12–13 · ISO 29100:2024.
  - **Dependencias:** `PRV-001` · **Prioridad:** P1 · **Complejidad:** M.
  - **Criterios de aceptación:** Alta de contacto y captura pública funcionan sin RUT; `legal_basis` acepta `consent`, `contract`, `legal_obligation`, `legitimate_interest`.
  - **Pruebas / DoD:** `test_tenant_upgrade_matrix.py` (`v3–v22`) y tests de captura/contactos verdes.
- **`PRV-011` · Recibos de consentimiento conformes a `ISO/IEC TS 27560:2023` y baja omnicanal**
  - **Objetivo:** Emitir registros y recibos JSON interoperables de consentimiento y propagar revocaciones a todos los canales del contacto.
  - **Alcance / Componentes:** `consent_authorization_service.py`, `api/v1/campaigns.py`, `frontend/app`.
  - **Normativa:** GDPR Art. 7 · Ley 21.719 Art. 12 · ISO/IEC TS 27560:2023 · ePrivacy.
  - **Dependencias:** `PRV-010` · **Prioridad:** P1 · **Complejidad:** M.
  - **Criterios de aceptación:** Endpoint `GET /api/v1/contacts/{id}/consent-receipts` retorna JSON conforme al esquema `TS 27560`; `BAJA` o unsubscribe bloquea email + WhatsApp para la finalidad revocada.
  - **Pruebas / DoD:** Validación contra JSON Schema `TS 27560` y test de bloqueo concurrente multicanal.
- **`PRV-012` · Aviso de privacidad por capas (`ISO 29184:2020`) y aviso obligatorio IA (`EU AI Act Art. 50`)**
  - **Objetivo:** Reemplazar el placeholder legal de la landing y añadir divulgación explícita de IA en Webchat, WhatsApp y Voz.
  - **Alcance / Componentes:** `frontend/landing/.../privacy-policy`, formulario de contacto (`accept_privacy_notice` + `notice_version`), `webchat_service.py`, `baileys-services`, `voice_service.py`.
  - **Normativa:** GDPR Art. 12–14 · Ley 21.719 Art. 14 ter · ISO/IEC 29184:2020 · **EU AI Act Art. 50 (vigente)**.
  - **Dependencias:** `PRV-002` · **Prioridad:** P1 · **Complejidad:** M.
  - **Criterios de aceptación:** Política muestra estructura completa (con marcadores claros para campos que debe completar el equipo legal del operador); Webchat y primer turno IA emiten aviso claro de interacción con IA.
  - **Pruebas / DoD:** Vitest en `frontend/landing` + tests en `webchat_service` y `baileys-services`.

> **Quality Gate `QG-3`:** Migración `v3–v22` verde, recibos `TS 27560` válidos, aviso IA Art. 50 presente en todos los canales automatizados.

---

### Ciclo 4 — Derechos de los Titulares (ARCOP + Bloqueo)
- **`PRV-013` · Exportación portable completa y solicitudes multicanal en Operational**
  - **Objetivo:** Permitir crear casos DSAR por `contact_id`, `email` o `whatsapp_id` y exportar la copia real (mensajes, transcripciones, pedidos, consentimientos, memoria) en JSON/CSV estructurado.
  - **Alcance / Componentes:** `privacy_case_service.py`, `api/v1/operational.py`, `frontend/app/.../privacy-cases-page`.
  - **Normativa:** GDPR Art. 15, 20 · Ley 21.719 Art. 5, 9.
  - **Dependencias:** `PRV-003` · **Prioridad:** **P0** · **Complejidad:** M.
  - **Criterios de aceptación:** `POST /export` incluye contenido completo de mensajes y metadatos del titular (excluyendo PII de terceros); soporta titulares sin WhatsApp.
  - **Pruebas / DoD:** Tests de portabilidad JSON + aislamiento multi-tenant.
- **`PRV-014` · Implementación de derechos de Rectificación, Oposición y Restricción/Bloqueo**
  - **Objetivo:** Completar el catálogo de derechos ARCOP+B más allá de acceso y supresión.
  - **Alcance / Componentes:** `clientes.processing_restricted` (`v22`), `privacy_case_service.py`, `outbox_dispatcher.py`, `agent_runtime.py`.
  - **Normativa:** GDPR Art. 16, 18, 21 · Ley 21.719 Art. 6, 8, 8 ter (bloqueo temporal).
  - **Dependencias:** `PRV-013` · **Prioridad:** P1 · **Complejidad:** M.
  - **Criterios de aceptación:** Activar `processing_restricted=True` bloquea campañas, workflows, inferencia IA y envíos salientes conservando los datos intactos hasta resolución del caso.
  - **Pruebas / DoD:** Tests verifican bloqueo efectivo en outbox, workflows y agente mientras `processing_restricted=True`.
- **`PRV-015` · DSAR de usuarios IAM (`auth-service`) y gestión de `iam_contact_message`**
  - **Objetivo:** Habilitar exportación y eliminación/anonimización de cuentas de usuario y mensajes del formulario público de contacto.
  - **Alcance / Componentes:** `backend/auth-service/apps/accounts/views.py`, `apps/contact/views.py`, `frontend/app/.../settings-page`.
  - **Normativa:** GDPR Art. 15, 17, 20 · Ley 21.719 Art. 5–9.
  - **Dependencias:** `PRV-001` · **Prioridad:** **P0** · **Complejidad:** M.
  - **Criterios de aceptación:** Endpoints autenticados `/api/v1/auth/me/export/` y `/api/v1/auth/me/erase/` (protegiendo invariante de último owner activo); endpoint administrativo de exportación y borrado de `iam_contact_message` por email.
  - **Pruebas / DoD:** Suite Django `manage.py test` cubriendo exportación, anonimización, revocación de sesiones y protección de último owner.
- **`PRV-016` · Explicabilidad e impugnación de decisiones automatizadas (Scoring / Workflows)**
  - **Objetivo:** Registrar factores de calificación (`score_factors_json`) y permitir marcar impugnación humana en leads/oportunidades.
  - **Alcance / Componentes:** `leads`, `lead_service.py`, `workflow_service.py`.
  - **Normativa:** GDPR Art. 22 · Ley 21.719 Art. 8 bis.
  - **Dependencias:** `PRV-014` · **Prioridad:** P2 · **Complejidad:** S.
  - **Criterios de aceptación:** El operador y el titular pueden consultar los criterios del score y solicitar revisión humana que pausa automatizaciones sobre ese lead.
  - **Pruebas / DoD:** Test de pausa de workflow ante `human_review_requested=True`.

> **Quality Gate `QG-4`:** 100% de derechos ARCOP+B ejecutables y verificados por pruebas automatizadas en Operational e IAM.

---

### Ciclo 5 — Gestión del Ciclo de Vida de los Datos
- **`PRV-017` · Política de retención configurable por tenant y barrido automático en `operational-worker`**
  - **Objetivo:** Automatizar la purga por TTL de mensajes, conversaciones, memoria IA, adjuntos expirados, transcripciones de voz, sesiones webchat y trazas.
  - **Alcance / Componentes:** `tenant_retention_policies` (`v22`), `privacy_case_service.py`, `app/worker.py`, `outbox_dispatcher.py`.
  - **Normativa:** GDPR Art. 5.1.e · Ley 21.719 Art. 3.f · ISO/IEC 29151:2026.
  - **Dependencias:** `PRV-003` · **Prioridad:** **P0** · **Complejidad:** L.
  - **Criterios de aceptación:** `operational-worker` ejecuta barridos periódicos respetando `legal_hold` (excepciones de retención) y registra conteos exactos en `log_limpiezas`.
  - **Pruebas / DoD:** Test de integración con reloj inyectado (`now`) comprueba purga exacta y respeto a `legal_hold`.
- **`PRV-018` · Retención en `auth-service` y purga diferida de schemas de tenants eliminados**
  - **Objetivo:** Depurar `iam_contact_message` (ej. 180 días), logs de login fallido (sin email en claro tras TTL) y purgar físicamente el schema PostgreSQL de tenants eliminados tras ventana de gracia (ej. 30 días).
  - **Alcance / Componentes:** `backend/auth-service/apps/tenants/`, `backend/operational-service/app/api/internal/tenants.py` (`DELETE /internal/tenants/{id}/purge`).
  - **Normativa:** GDPR Art. 5.1.e, 28.3.g · Ley 21.719 Art. 25.
  - **Dependencias:** `PRV-015`, `PRV-017` · **Prioridad:** **P0** · **Complejidad:** M.
  - **Criterios de aceptación:** Tenant eliminado pasa a `pending_purge`, queda bloqueado inmediatamente y se purga con `DROP SCHEMA ... CASCADE` + registro de certificado de destrucción tras vencer la ventana de gracia.
  - **Pruebas / DoD:** Test de ciclo completo: eliminación → bloqueo → purga → verificación de inexistencia de schema.
- **`PRV-019` · Sanitización PII en logs y tabla *Tombstones* post-restore de backups**
  - **Objetivo:** Evitar PII en logs de aplicación y prevenir la "resurrección" de titulares borrados al restaurar un respaldo PostgreSQL.
  - **Alcance / Componentes:** Filtros de logging en `auth-service`, `operational-service`, `agent-core`; `privacy_erasure_tombstones` + script `reapply_erasure_tombstones.py` integrado en runbook de restore.
  - **Normativa:** GDPR Art. 17, 32 · ISO/IEC 27001 A.8.13/A.8.15.
  - **Dependencias:** `PRV-003` · **Prioridad:** P1 · **Complejidad:** M.
  - **Criterios de aceptación:** Logs estructurados enmascaran emails/RUTs/tokens; test de `pg_dump`/`pg_restore` (`test_operational_restore.py`) reaplica tombstones y verifica 0 resurrección de PII.
  - **Pruebas / DoD:** `test_operational_restore.py` ampliado y verde en CI.

> **Quality Gate `QG-5`:** Retención automática verificada en Operational e IAM, purga de tenant eliminados probada y restore sin resurrección de datos borrados.

---

### Ciclo 6 — Proveedores, Integraciones, Menores y Datos Sensibles
- **`PRV-020` · Registro de subencargados por tenant y control de transferencias internacionales**
  - **Objetivo:** Exigir habilitación consciente y auditable de cada proveedor externo (Groq, Resend, Meta, Twilio, Shopify, Mercado Pago, Google, HubSpot, MCP remoto) con jurisdicción visible.
  - **Alcance / Componentes:** `tenant_subprocessor_approvals`, `channel_connection_service.py`, `mcp_client_service.py`, `frontend/app`.
  - **Normativa:** GDPR Art. 28, 44–49 · Ley 21.719 Art. 25, 27 · ISO/IEC 27701:2025.
  - **Dependencias:** `PRV-004` · **Prioridad:** P1 · **Complejidad:** M.
  - **Criterios de aceptación:** No se puede activar una conexión externa sin registrar aprobación del `TENANT_OWNER` con fecha y versión de listado de subencargados.
  - **Pruebas / DoD:** Tests de API confirman `403/422` sin aprobación previa y registro en auditoría al aprobar.
- **`PRV-021` · Detección de datos sensibles y protección de menores en ingesta y adjuntos**
  - **Objetivo:** Alertar y proteger flujos ante entrada espontánea de datos sensibles (salud, tarjetas, menores) en chat, voz o formularios.
  - **Alcance / Componentes:** `ingest_service.py`, `webchat_service.py`, `pii_scrubber.py`.
  - **Normativa:** GDPR Art. 8, 9 · Ley 21.719 Art. 16, 16 bis · ISO/IEC 31700.
  - **Dependencias:** `PRV-005` · **Prioridad:** P2 · **Complejidad:** M.
  - **Criterios de aceptación:** Patrones de alto riesgo (tarjetas, palabras clave configurables de datos sensibles) activan redacción pre-LLM y flag de revisión humana sin romper la conversación.
  - **Pruebas / DoD:** Tests unitarios con payloads sintéticos sensibles.
- **`PRV-022` · Deduplicación distribuida de webhooks en `mail-service` (Redis)**
  - **Objetivo:** Eliminar la pérdida de deduplicación de webhooks Resend al reiniciar o escalar réplicas (actualmente en memoria de proceso).
  - **Alcance / Componentes:** `backend/mail-service/app/webhooks.py`.
  - **Normativa:** ISO/IEC 27001 A.8.16 · Integridad de recibos/bajas.
  - **Dependencias:** Ninguna · **Prioridad:** P2 · **Complejidad:** S.
  - **Criterios de aceptación:** Deduplicación en Redis con TTL configurable y fallback controlado solo en desarrollo local.
  - **Pruebas / DoD:** `pytest` en `backend/mail-service` verde.

> **Quality Gate `QG-6`:** Ningún conector/MCP externo opera sin aprobación de subencargado; datos sensibles filtrados antes de LLM; webhooks `mail-service` persistentes en Redis.

---

### Ciclo 7 — Gobernanza, Auditoría Inmutable, DPIA e Incidentes
- **`PRV-023` · Integridad de auditoría (hash chain) y registro de accesos de lectura a PII**
  - **Objetivo:** Garantizar trazabilidad verificable de quién consultó o exportó PII y detectar alteraciones en logs de auditoría.
  - **Alcance / Componentes:** `backend/operational-service/app/services/audit_event_service.py`, `log_limpiezas`, `backend/auth-service/apps/audit/`.
  - **Normativa:** GDPR Art. 5.2, 32 · ISO/IEC 27001 A.8.15 · ISO/IEC 27701.
  - **Dependencias:** `PRV-019` · **Prioridad:** P2 · **Complejidad:** M.
  - **Criterios de aceptación:** Cada registro de `log_limpiezas` incluye `prev_hash` y `entry_hash` (SHA-256) verificable por endpoint/CLI; cada consulta a `/export` o ficha sensible emite evento `privacy.pii.accessed`.
  - **Pruebas / DoD:** Test detecta manipulación de fila intermedia en cadena de hash.
- **`PRV-024` · Registro de incidentes de seguridad/privacidad y runbook SLA (3h CSIRT / 72h GDPR)**
  - **Objetivo:** Proveer registro estructurado de incidentes, cálculo automático de plazos de notificación y runbook operativo.
  - **Alcance / Componentes:** `security_incidents` (IAM/Operational), API restringida a plataforma/owner, actualización de `SECURITY.md` con runbook de respuesta y plantillas de notificación (Ley 21.663 3h / GDPR Art. 33 72h / Ley 21.719).
  - **Normativa:** **Ley 21.663 Chile (vigente)** · GDPR Art. 33–34 · Ley 21.719 Art. 14 sexies · ISO/IEC 27001 A.5.24–A.5.28.
  - **Dependencias:** `PRV-002` · **Prioridad:** P1 · **Complejidad:** M.
  - **Criterios de aceptación:** Crear incidente calcula automáticamente `csirt_early_warning_due_at` (+3h) y `authority_notice_due_at` (+72h), registra evidencias y estado de contención. *(Notificación real ante autoridades requiere validación legal/humana.)*
  - **Pruebas / DoD:** Tests de cálculo de SLA, RBAC estricto y simulacro documentado.
- **`PRV-025` · Plantilla DPIA (`ISO/IEC 29134:2023`) y Paquete de Evidencias PIMS (`ISO/IEC 27701:2025`)**
  - **Objetivo:** Documentar evaluación de impacto para IA conversacional, Voz/Twilio, Omnicanal y Transferencias Internacionales.
  - **Alcance / Componentes:** Sección/plantilla versionada para revisión con asesoría jurídica/DPO.
  - **Normativa:** GDPR Art. 35 · Ley 21.719 Art. 15 ter · ISO/IEC 29134:2023 · ISO/IEC 27701:2025.
  - **Dependencias:** `PRV-001`, `PRV-020` · **Prioridad:** P1 · **Complejidad:** S.
  - **Criterios de aceptación:** Cubre necesidad, proporcionalidad, riesgos a titulares, medidas técnicas y firma pendiente de DPO/legal.
  - **Pruebas / DoD:** Revisión de completitud contra cláusulas ISO/IEC 29134:2023.

> **Quality Gate `QG-7`:** Cadena de integridad verificada, SLA 3h/72h probado y plantilla DPIA lista para firma jurídica.

---

### Ciclo 8 — Automatización del Cumplimiento (*Compliance as Code*) y CI
- **`PRV-026` · Privacy Quality Gates automáticos en `.github/workflows/validate.yml`**
  - **Objetivo:** Impedir regresiones de privacidad en cualquier PR futuro.
  - **Alcance / Componentes:** `.github/workflows/validate.yml`, scripts de verificación de inventario PII, headers CSP/HSTS, pruebas negativas de `/erase` y `pii_scrubber`.
  - **Normativa:** ISO/IEC 31700-1:2023 · NIST Privacy Framework · Accountability.
  - **Dependencias:** Ciclos 1–7 · **Prioridad:** P1 · **Complejidad:** M.
  - **Criterios de aceptación:** CI falla automáticamente si: (a) se añade columna PII sin inventario, (b) `/erase` deja residuos, (c) `pii_scrubber` filtra PII, (d) falta CSP en Nginx, o (e) falla `gitleaks`/`pip-audit`/`npm audit`.
  - **Pruebas / DoD:** Corrida verde de `Validate` con job `privacy-compliance` activo.
- **`PRV-027` · Retiro de excepción temporal `picomatch` y SBOM automatizado**
  - **Objetivo:** Cerrar la excepción de desarrollo `GHSA-fc5q-39xc-vjpf` antes del 18 dic 2026 y generar SBOM (CycloneDX) por release.
  - **Alcance / Componentes:** `frontend/app`, `frontend/landing`, `.github/scripts/check-dev-audit.mjs`, `THIRD_PARTY.md`.
  - **Normativa:** ISO/IEC 27001 A.8.8 (gestión de vulnerabilidades técnicas) · Apache-2.0.
  - **Dependencias:** Ninguna · **Prioridad:** P1 · **Complejidad:** S.
  - **Criterios de aceptación:** `npm audit` limpio sin excepciones vencidas y artefacto SBOM generado en CI.
  - **Pruebas / DoD:** `web` jobs verdes en `Validate`.

> **Quality Gate `QG-8`:** Todos los controles de *Compliance as Code* corren en cada push/PR en `Validate` sin bypasses.

---

### Ciclo 9 — Validación Integral y Preparación para Producción
- **`PRV-028` · Ensayo de Backup/Restore cifrado + Reaplicación de *Tombstones* (`FK-15`)**
  - **Objetivo:** Medir RPO/RTO reales en entorno aislado y comprobar cero resurrección de datos suprimidos.
  - **Alcance / Componentes:** `deploy/`, `test_operational_restore.py`, `RELEASE_READINESS.md`.
  - **Normativa:** GDPR Art. 32.1.c · ISO/IEC 27001 A.8.13.
  - **Dependencias:** `PRV-019`, `QG-8` · **Prioridad:** P0 (pre-producción) · **Complejidad:** M.
  - **Criterios de aceptación:** Evidencia registrada de SHA, tiempo de restauración, verificación de integridad y 0 PII resucitada.
  - **Pruebas / DoD:** Acta técnica de ensayo de recuperación.
- **`PRV-029` · Cierre de Gates Externos (Jurídico, Contractual y Sandboxes Reales)**
  - **Objetivo:** Formalizar las obligaciones no técnicas antes del anuncio de producción estable.
  - **Alcance:** Revisión legal de Políticas/Términos; firma de DPAs/SCC/TIA (Groq, Resend, Meta, Twilio, Google, Shopify, Mercado Pago, HubSpot); homologación WhatsApp en cuentas autorizadas (`FK-14`); designación de DPO y aprobación de DPIA.
  - **Normativa:** GDPR · Ley 21.719 · Ley 21.663 · EU AI Act.
  - **Dependencias:** `PRV-025`, `PRV-028` · **Prioridad:** P0 (pre-producción) · **Complejidad:** Organizacional.
  - **Criterios de aceptación:** Evidencia documental archivada por el responsable legal/operador (fuera del repositorio público).

> **Quality Gate `QG-9` (Go/No-Go Producción):** `QG-0` a `QG-8` en verde + ensayo `FK-15` documentado + sign-off jurídico/contractual completo.

---

## 3. Estrategia de Pruebas de Privacidad y Cumplimiento

| Nivel | Qué valida | Herramienta / Suite | Frecuencia |
| --- | --- | --- | --- |
| **Paridad de inventario** | 100% de columnas PII en SQLAlchemy/Django declaradas en `compliance/data_inventory.yaml` | `unittest` + Django `test` | Cada PR (`Validate`) |
| **Pruebas negativas de borrado (`/erase`)** | 0 ocurrencias de RUT, email, teléfono y contenido de mensajes en **todas** las tablas tenant + IAM | `unittest` sobre PG18 temporal | Cada PR (`Validate`) |
| **Pruebas de egreso IA/MCP** | Bloqueo por defecto (`allow_external_ai_transfer=false`) + *PII Scrubber* en 100% de payloads salientes | `pytest` (`agent-core`) + `unittest` (`operational`) | Cada PR (`Validate`) |
| **Aislamiento multi-tenant** | IDs coincidentes en 2 tenants nunca filtran datos en tablas `tenant_*` ni `public` | `test_tenant_upgrade_matrix.py` + suite RBAC IAM | Cada PR (`Validate`) |
| **Retención y Restore** | Purga automática por TTL, respeto a `legal_hold` y cero resurrección tras `pg_dump`/`pg_restore` | `test_operational_restore.py` + worker cycle test | Cada PR + pre-release |
| **Seguridad y secretos** | CSP/HSTS, `gitleaks`, `pip-audit`, `npm audit`, rechazo de refresh tokens | `Validate` CI + smoke E2E estándar/demo | Cada PR (`Validate`) |
