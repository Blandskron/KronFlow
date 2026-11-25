# Testing

## Objetivo

La suite debe proteger comportamiento IAM crítico:

- Alta manual
- Verificación de email y activación de cuenta
- Onboarding de tenant inicial
- Invitaciones de usuarios existentes y nuevos
- Login
- Perfiles
- Tenants
- RBAC
- Sesiones
- MFA
- API keys
- Service accounts
- Signing keys
- Introspection
- Auditoría
- Aislamiento tenant

## Comandos

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

## Tests actuales

La suite versionada contiene 20 métodos `test_*` y cubre:

- Creación automática de `UserProfile` mediante señal al crear un usuario nativo de Django.
- Formulario de contacto público: exigencia de CSRF, creación exitosa con token válido y rechazo de payloads con HTML malicioso.
- Seed de roles y permisos del tenant, y limitación de permisos RBAC según el plan activo (entitlements).
- Rotación de signing keys y mantenimiento de la clave anterior como inactiva en el JWKS para compatibilidad de firmas.
- Emisión de token M2M (client credentials) introspectable y restringido por scopes.
- Introspection de tokens restringida al scope `auth.verify_token` de service accounts.
- API keys: hasheo de claves, revocación física y lógica, y generación segura en rotación.
- Detección de riesgo de sesión (flag `NEW_DEVICE` y score de riesgo positivo en primer dispositivo).
- Middleware y permisos: exigencia de coincidencia entre el tenant del token/membresía y el solicitado (`HasTenantPermission`).
- Control de entitlements de suscripción dinámicos ante cambios de plan del tenant.
- Hardening de seguridad: exigencia de claim `amr` (MFA) para acciones críticas (`RequiresMfaForCriticalAction`).
- Registro de contexto de dispositivo (IP address y User Agent) al crear una `UserSession`.
- Flujo de login y onboarding de empresa para un usuario verificado sin tenant activo.
- Validación de invitaciones: requerir que el usuario que acepta la invitación coincida con el email invitado.
- Aceptación de invitación para un usuario nuevo, permitiendo la activación de la cuenta mediante token válido.
- Bloqueo para evitar la degradación o remoción del último `TENANT_OWNER` activo en el tenant.
- Redirección de rutas desconocidas al Swagger UI (/api/docs/).

El conteo describe casos reales implementados y probados. No hay una configuración de coverage/versionado que permita declarar un porcentaje exacto.

## Estrategia recomendada

### Unit tests

Para:

- servicios puros
- calculo de permisos
- hashing y rotacion
- risk engine
- serializers

### Integration tests

Para:

- endpoints de auth
- endpoints tenantizados
- API keys
- service accounts
- introspection
- admin commands

### Security tests

Para:

- acceso cross-tenant denegado
- accion critica sin MFA denegada
- token con sesion revocada inactivo
- secret invalido falla
- scope no permitido falla
- API key revocada no usable
- comportamiento de refresh reuse cuando se conecte al flujo HTTP

## Datos de prueba

Preferir factories futuras para:

- user
- profile
- tenant
- membership
- role
- permission
- session
- signing key
- service account
- API key

## Criterio de aceptacion

Un cambio no deberia considerarse listo si:

- falla `manage.py check`
- hay migraciones pendientes
- falla un test
- cambia contrato HTTP sin actualizar docs/OpenAPI
- introduce operacion sensible sin auditoria
- reduce aislamiento tenant

## Pruebas futuras recomendadas

- login con MFA obligatorio
- login, refresh y logout end-to-end
- reset password invalida sesiones
- logout all revoca sesiones
- revocacion de API key
- endpoints de invitación y administración de miembros
- login con `onboarding_required=true` para usuario verificado sin tenant
- `POST /api/v1/tenants/onboarding/` crea tenant, owner y tokens tenantizados
- rechazo de onboarding si email no esta verificado
- aceptacion de invitacion exige email coincidente en usuario existente
- invitacion con usuario nuevo crea cuenta solo con token valido
- bloqueo de remocion/degradacion del ultimo owner
- CRUD tenant/RBAC con aislamiento cross-tenant
- aprovisionamiento operacional, timeout, 502 y reintento
- uploads inválidos y límites de tamaño
- JWKS/validación de ambas familias de claves documentadas
- detección real de refresh reuse (hoy no conectada al endpoint)
- seeds idempotentes
- entrypoint con flags desactivados
- comandos de superuser idempotentes
