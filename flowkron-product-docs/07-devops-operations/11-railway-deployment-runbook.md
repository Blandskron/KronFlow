# Runbook técnico de despliegue Railway

Versión: 1.0
Tipo: procedimiento técnico
Estado: `PARTIAL`
Última verificación: 2026-07-23

La presencia de `railway.toml` y Dockerfiles permite preparar un despliegue, pero no demuestra que exista un ambiente Railway activo o validado.

## 1. Servicios con configuración

| Repositorio | Build | Health path configurado |
| --- | --- | --- |
| Auth | Dockerfile | `/healthz/` |
| Operational | Dockerfile | `/healthz` |
| Agent Core | Dockerfile | `/healthz` |
| App | Dockerfile/Nginx | `/` |
| Landing | Dockerfile/Nginx | `/health/` |


## 2. Dependencias

- PostgreSQL accesible por Auth y Operational.
- Redis accesible por Auth.
- Clave JWT privada solo en Auth.
- Clave pública JWT en Operational y Agent Core.
- `INTERNAL_TOKEN` consistente entre Auth, Operational y Agent Core.
- SMTP para verificación/invitaciones/reset.
- URLs públicas de Auth, Operational, Agent Core, App y Landing.
- Storage persistente para media/claves si el diseño Railway lo requiere.

## 3. Orden recomendado

1. Crear PostgreSQL y Redis.
2. Desplegar Auth.
3. Ejecutar migraciones/seeds autorizados.
4. Verificar health, JWKS/login y SMTP.
5. Desplegar Operational.
6. Verificar JWT, ready y provisioning tenant.
7. Desplegar Agent Core.
8. Verificar health, contexto y conexión interna.
9. Construir Landing/App con URLs públicas finales.
10. Ejecutar smoke end-to-end.

## 4. Configuración por servicio

Use `.env.example` y los documentos `CONFIGURATION`/`DEPLOYMENT` de cada repositorio. No copie secretos a Railway templates versionados.

Para frontends, las URLs son build args públicos. Cambiarlas exige reconstruir:

- App: Auth, Operational, Agent Core y Landing.
- Landing: App y base de contacto Auth.

## 5. Migraciones

### Auth

- Ejecutar migrations Django.
- Verificar que no haya migraciones pendientes.
- Sembrar roles/permisos solo con comandos idempotentes autorizados.

### Operational

- Verificar tablas públicas.
- Provisionar un tenant descartable.
- Ejecutar migración de todos los tenants cuando cambie DDL activo.
- No usar scripts destructivos sobre una DB compartida.

## 6. Smoke

- Health de los cinco servicios.
- Landing y App cargan.
- CORS correcto.
- Contacto CSRF.
- Login, refresh y `/auth/me`.
- Onboarding/provisioning.
- Leads/conversaciones/analytics.
- Plantillas, upload, status y simulate.
- Aislamiento entre dos tenants.
- Logs sin secretos.

## 7. Rollback

- Conservar imagen/commit anterior.
- No mezclar deploy con migraciones irreversibles.
- Tomar backup verificado antes de cambios de datos.
- Revertir URLs frontend reconstruyendo el artefacto anterior.
- Validar compatibilidad DB antes de bajar versión.

## 8. Riesgos abiertos

- Healthchecks superficiales.
- Persistencia de claves/media.
- Sin pipeline ni promoción automatizada.
- Sin observabilidad/alertas.
- Sin backup/restore probado.
- Sin evidencia de despliegue remoto aprobada.

