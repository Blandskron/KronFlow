# Plantilla DPIA (`ISO/IEC 29134:2023`) y Paquete de Evidencias PIMS (`ISO/IEC 27701:2025`) — KronFlow

> **Estado:** Plantilla técnica lista para revisión y firma del Delegado de Protección de Datos (DPO / Encargado de Prevención Ley 21.719) y asesoría jurídica del operador.

---

## 1. Identificación del Tratamiento (ISO/IEC 29134:2023 §6.2)

- **Sistema:** KronFlow — Intelligent CRM (`tenant_schema_v22`)
- **Operador / Responsable (IAM y Landing):** `[Completar Razón Social]`
- **Encargado de Protección de Datos (DPO):** `[Completar Nombre y Correo DPO]`
- **Fecha de evaluación:** `[YYYY-MM-DD]`
- **Actividades cubiertas:**
  1. IA Conversacional (RAG, memoria conversacional opcional, propuestas HITL `at-most-once` y egreso opcional a LLM externo Groq).
  2. Canal de Voz programable (Twilio, transcripciones y consentimiento explícito de grabación).
  3. Mensajería omnicanal (WhatsApp, Webchat embebible, Meta Instagram/Messenger y Correo transaccional/campañas).
  4. Transferencias internacionales a subencargados aprobados por tenant (`tenant_subprocessor_approvals`).

---

## 2. Necesidad, Proporcionalidad y Minimización (§6.3)

- **Bases de licitud:** Consentimiento explícito (recibos `ISO/IEC TS 27560:2023`), ejecución de contrato, obligación legal e interés legítimo registrados por finalidad en `contact_consent_decisions.legal_basis`.
- **Minimización:** `clientes.rut` es opcional (`nullable=True`); cuando se recopila, se protege con cifrado autenticado (`rut_encrypted`) y búsqueda exacta por índice ciego HMAC-SHA256 (`rut_blind_index`).
- **Privacy by Default:** `allow_external_ai_transfer=False` y `memory_auto_capture=False` por defecto en todo tenant nuevo.
- **Plazos de conservación:** Configurables por tenant (`tenant_retention_policies`) con barrido automático en `operational-worker`, soporte de `legal_hold`, retención IAM (`run_iam_retention`) y *tombstones* post-restore (`privacy_erasure_tombstones`).

---

## 3. Evaluación de Riesgos para los Titulares y Medidas Técnicas (§6.4)

| Riesgo identificado | Prob. inherente | Impacto | Controles técnicos implementados en KronFlow | Riesgo residual |
| --- | --- | --- | --- | --- |
| Fuga de PII hacia LLM/MCP externos | Alta | Crítico | Gate `allow_external_ai_transfer=False` por defecto + `pii_scrubber.py` pre-egreso (RUT, email, teléfono, PAN Luhn) + aprobación explícita de subencargados | Bajo |
| Ingesta espontánea de datos sensibles o de menores | Media | Alto | `detect_sensitive_data` (salud, menores, tarjetas) deriva inmediatamente a humano (`sensitive_data_detected`) sin pasar por LLM externo | Bajo |
| Fuga de PII residual tras supresión (`/erase`) | Alta | Crítico | Anonimización completa multi-tabla (incl. RUT), supresión omnicanal (`email` + `whatsapp`), *tombstones* post-restore y prueba negativa de cero residuos | Bajo |
| Falta de transparencia IA (EU AI Act Art. 50) | Alta | Alto | Divulgación explícita `ai_disclosure` en Webchat y saludos/respuestas de `agent-core` + política por capas `ISO/IEC 29184:2020` | Bajo |
| Secuestro de sesión o acceso post-revocación | Media | Alto | CSP estricta sin `unsafe-eval` + HSTS en Nginx, revocación inmediata JWT vía Redis (`jti`/sesión/usuario/tenant) y soporte cookie `HttpOnly; SameSite=Lax` | Bajo |
| Incumplimiento de notificación de brechas (3h/72h) | Media | Crítico | Registro `public.security_incidents` con cálculo automático de SLA (+3h CSIRT Ley 21.663 / +72h GDPR-Ley 21.719) y runbook en `SECURITY.md` | Bajo (requiere simulacro organizacional) |

---

## 4. Índice de Evidencias PIMS (`ISO/IEC 27701:2025`)

- **Inventario de datos (RoPA):** `compliance/data_inventory.yaml` + pruebas de paridad CI (`test_pii_inventory_parity.py`, `apps/audit/tests.py`).
- **Aislamiento multi-tenant:** `schema_translate_map` + `test_tenant_upgrade_matrix.py`.
- **Derechos ARCOP+B:** `/privacy-cases`, `/export`, `/erase`, `/rectify`, `/restrict`, `/api/v1/auth/me/export/`, `/api/v1/auth/me/erase/`, `/api/v1/contact/messages/dsar/`.
- **Integridad de auditoría:** Cadena SHA-256 verificable en `log_limpiezas` (`/log-limpiezas/verify-chain`) y eventos `privacy.pii.accessed`.
- **Subencargados:** `tenant_subprocessor_approvals` (`/api/v1/operational/subprocessors`).

---

## 5. Aprobación y Firma (Pendiente de Validación Jurídica / DPO)

- [ ] Revisado por **DPO / Encargado de Prevención de Delitos de Datos**: `_____________________` · Fecha: `____-__-__`
- [ ] Revisado por **Asesoría Jurídica (DPAs / SCC / TIA verificados)**: `_____________________` · Fecha: `____-__-__`
- [ ] Aprobado por **Dirección / Propietario del Servicio**: `_____________________` · Fecha: `____-__-__`
