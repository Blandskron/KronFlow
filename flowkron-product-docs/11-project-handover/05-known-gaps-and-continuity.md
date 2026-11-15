# Deuda técnica y continuidad

## 1. Riesgos prioritarios

| Prioridad | Brecha | Riesgo técnico | Criterio de cierre |
| --- | --- | --- | --- |
| P0 | Sin autorización granular en Operational | Acceso excesivo dentro del tenant | Permisos por endpoint y tests negativos |
| P0 | Cobertura cross-tenant incompleta | Fuga de datos | Suite automática con dos tenants |
| P0 | Sin secrets/TLS productivo | Compromiso de credenciales/tráfico | Secret manager, TLS y rotación |
| P0 | Sin backup/restore probado | Pérdida de datos | Backup cifrado y restore verificado |
| P1 | Migraciones tenant aditivas | Drift y fallos de schema | Revisiones versionadas y rollback |
| P1 | Sin CI/CD/staging | Releases manuales no repetibles | Pipeline con gates y rollback |
| P1 | Sin observabilidad | Fallos no detectados | Métricas, logs, traces y alertas |
| P1 | Revocación JWT parcial | Tokens activos tras riesgo | Enforcement consistente |
| P2 | IA sin evaluación/costos | Calidad y gasto desconocidos | Dataset, métricas y budgets |
| P2 | Stubs/placeholders | Contratos/UI engañosos | Implementar, retirar o etiquetar |

## 2. Deuda por servicio

### Auth

- Revocación no consultada en cada request.
- Refresh reuse no conectado completamente.
- Dos familias de signing keys/JWKS.
- Healthchecks superficiales.
- Dependencia síncrona de Operational.

### Operational

- Sin pytest/suite automática.
- Sin RBAC granular.
- Agentes stub.
- Rate limit en memoria por proceso.
- Alembic sin revisiones y tenant migrations parciales.
- Modelos legacy coexistiendo con activos.

### Agent Core

- Adaptadores Operational incompletos para rutas stateful.
- Retrieval lexical, sin vector store.
- Sin evaluación/costos/observabilidad IA.
- Provider real no cubierto por tests.

### App

- Sin tests unitarios Angular.
- Conversaciones solo lectura.
- Workflows derivado.
- Integraciones/notificaciones placeholder.
- Tokens en `localStorage`.

### Landing

- Sin tests unitarios.
- Smoke sin baseline visual.
- Dependencia externa Google Fonts.
- Controles de accesibilidad incompletos.

### Deploy

- Solo local.
- Automation opcional.
- Puertos publicados y HTTP.
- Sin observabilidad, backups o CI/CD.

### Contracts

- Gateway WhatsApp sin paths.
- Sin lint semántico OpenAPI completo en pipeline.
- Falta prueba automática contrato-runtime-consumidor.

## 3. Checklist de entrega técnica

- [x] Mapa de repositorios y owners.
- [x] Arquitectura y fronteras de confianza.
- [x] Flujos críticos.
- [x] Ownership de datos.
- [x] Contratos y autenticación.
- [x] Configuración local documentada.
- [x] Matriz de tests y brechas.
- [x] Riesgos y modos legacy.
- [ ] Inventario de secretos y accesos transferido por canal seguro.
- [ ] Ambientes remotos inventariados.
- [ ] Staging reproducible.
- [ ] Backup/restore probado.
- [ ] Tests cross-tenant.
- [ ] E2E integrado.
- [ ] Runbook de incidentes y on-call.

## 4. Orden de continuidad

1. Aislamiento, autorización, secrets y backups.
2. Migraciones tenant.
3. Staging y CI/CD.
4. Observabilidad.
5. Contratos y E2E.
7. Cierre de stubs y deuda IA.

