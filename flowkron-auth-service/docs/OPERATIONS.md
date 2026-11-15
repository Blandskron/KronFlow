# Operación, checklist y runbooks

Este documento consolida la antigua guía de operaciones, los runbooks y el checklist de producción.

## Comprobaciones rutinarias

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
python manage.py collectstatic --noinput
docker compose config
```

Los endpoints `GET /health/` y `GET /healthz/` devuelven `{"status":"ok"}` y sirven como liveness superficial. No validan DB, Redis, migraciones ni signing keys; configura readiness externa con esas dependencias si la plataforma lo requiere.

## Bootstrap y seeds

```powershell
python manage.py migrate
python manage.py seed_iam
python manage.py seed_iam_advanced
python manage.py ensure_superuser --email $env:DJANGO_SUPERUSER_EMAIL --password $env:DJANGO_SUPERUSER_PASSWORD
```

`seed_iam` crea permisos/roles base para tenants existentes. `seed_iam_advanced` crea los recursos avanzados definidos por su comando, incluida una signing key inicial si corresponde. Nunca copies credenciales desde la documentación.

## Docker local vs stack monorepo

El `docker-compose.yml` propio de este repositorio nombra el servicio web como `app`. El stack integrado de `flowkron-deploy` lo nombra `flowkron-auth-service`. Ajusta los comandos segun el compose desde el que estes operando:

```powershell
docker compose exec -T app python manage.py check
docker compose exec -T flowkron-auth-service python manage.py check
```

## Señales operacionales

- Logs JSON en stdout con `level`, `logger`, `message` y `time`.
- `X-Request-ID` se genera o conserva; `X-Correlation-ID` se conserva o deriva del request ID.
- `AuditLog` se escribe sincrónicamente en PostgreSQL.
- Eventos prioritarios: `login_failed`, `session_compromised`, `signing_key_rotated`, `api_key_created`, `api_key_revoked`, `service_account_created` y `session_risk_detected`.

## Runbook: login bloqueado

1. Verificar `/healthz/` o `/health/`, proceso web y PostgreSQL.
2. Buscar `login_failed` y bloqueos de django-axes.
3. Comprobar `is_active`, `email_verified_at`, tenant activo y membership activa.
4. Si MFA está activo, revisar sincronización horaria y TOTP.
5. No desactivar validadores ni marcar correos como verificados sin autorización.

## Runbook: verificacion de correo no llega

1. Revisar logs `apps.security.services` para errores SMTP.
2. Confirmar que el stack real este usando el `.env` del despliegue y no un `.env` aislado.
3. Verificar `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_USE_TLS`, `EMAIL_USE_SSL` y `DEFAULT_FROM_EMAIL`. Para cPanel/correo SSL directo usar `EMAIL_PORT=465`, `EMAIL_USE_SSL=True` y `EMAIL_USE_TLS=False`.
4. Probar login SMTP desde el contenedor:

```powershell
docker compose exec -T flowkron-auth-service python manage.py test_smtp
```

En el compose local del repo, usa `app` en lugar de `flowkron-auth-service`.

5. Si devuelve `SMTP_AUTH_FAILED code=535`, Django ya llego al servidor SMTP y el bloqueo esta en el proveedor: password invalida, autenticacion SMTP deshabilitada para el buzon o politica de seguridad bloqueando el login.
6. En despliegue local, `EMAIL_LOG_TOKEN_ON_FAILURE=True` permite ver el token generado en logs cuando SMTP falla. Usarlo solo en desarrollo.
7. Si SMTP esta caido en desarrollo, generar token manual con:

```powershell
docker compose exec -T flowkron-auth-service python manage.py send_email_verification --email usuario@example.com --print-token
```

En el compose local del repo, usa `app` en lugar de `flowkron-auth-service`.

8. No registrar tokens en tickets, logs compartidos ni documentacion.
9. Cuando SMTP vuelva a estar operativo, reenviar sin `--print-token`.
10. El correo de verificacion debe incluir un boton a `APP_PUBLIC_URL/confirm-email?token=...`; revisar `APP_PUBLIC_URL` si el enlace apunta al host incorrecto.

## Runbook: tokens rechazados

1. Consultar `/api/v1/auth/jwks/`.
2. Validar `alg=RS256`, `iss=flowkron-auth-service`, `aud=flowkron`, `exp` y `kid` cuando exista.
3. Para tokens humanos, comprobar que `session_id` siga activo mediante introspection autorizada o `/api/v1/sessions/status/`.
4. Recordar que Simple JWT humano usa el par configurado por settings; los tokens de service account usan `iam_signing_key`. JWKS publica solo estas últimas.

## Runbook: API key expuesta

1. Identificar tenant e ID/prefix sin registrar la key completa.
3. Crear/rotar una reemplazante si la integración debe continuar.
4. Revisar auditoría y el consumidor real. Este servicio no valida `Authorization: ApiKey`; coordina también la revocación en el gateway/servicio que sí la consuma.

## Runbook: rotación de signing key

1. Confirmar que los consumidores de service-account tokens usan JWKS por `kid`.
3. Verificar nueva clave activa y anterior inactiva con expiración de compatibilidad.
4. Comprobar JWKS y errores de validación. Mantener estable `SIGNING_KEY_ENCRYPTION_KEY`.

## Runbook: aprovisionamiento operacional

Ante `OPERATIONAL_PROVISION_FAILED` o 502:

1. Verificar `OPERATIONAL_SERVICE_URL`, conectividad y que el servicio operacional responda.
2. Verificar que ambos servicios compartan el mismo `OPERATIONAL_INTERNAL_TOKEN`, sin imprimirlo.
3. Revisar `TenantOperationalRuntime.status`, `last_sync_at` y `last_error`.
4. Reintentar `POST /api/v1/tenants/{id}/runtime/provision/` solo después de corregir la causa.
5. La activación de suscripción también aprovisiona sincrónicamente y puede fallar después de persistir datos de suscripción; revisar ambos estados antes de repetir.

## Backup y restauración

Respaldar PostgreSQL, el par JWT configurado y secretos de cifrado. Sin `SIGNING_KEY_ENCRYPTION_KEY` no se recuperan claves privadas administradas. No existen copias en claro de API keys, client secrets, recovery codes ni tokens de un solo uso.

Orden de restauración: DB, secretos/llaves, versión compatible, migraciones, seeds idempotentes y smoke tests de `/healthz/` o `/health/`, `/api/schema/`, `/api/v1/auth/jwks/`, login y client credentials.

## Checklist de producción

- [ ] `DJANGO_SETTINGS_MODULE=config.settings.base`, `DJANGO_DEBUG=False` y secreto Django fuerte.
- [ ] Hosts, CORS/CSRF y proxy HTTPS configurados explícitamente.
- [ ] PostgreSQL/Redis privados, con backups, restore probado y monitoreo.
- [ ] Par JWT y `SIGNING_KEY_ENCRYPTION_KEY` persistentes en secret manager.
- [ ] `OPERATIONAL_INTERNAL_TOKEN` no usa el default local y coincide entre servicios.
- [ ] `CREATE_SUPERUSER` desactivado tras bootstrap y administradores con MFA.
- [ ] Migraciones ejecutadas una vez por release; seeds y `collectstatic` verificados.
- [ ] Swagger/admin restringidos según política; health/readiness y alertas configurados.
- [ ] Pruebas, smoke tests y rotación/revocación ensayadas sin datos productivos.
