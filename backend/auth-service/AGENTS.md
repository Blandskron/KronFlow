# AGENTS.md

Fuente única de contexto e instrucciones para asistentes de IA que trabajen en `flowkron-auth-service`. Los adaptadores `CLAUDE.md` y `GEMINI.md` solo remiten aquí.

## Propósito y límites


No asumas capacidades inexistentes:

- Las API keys se crean, rotan y revocan aquí, pero no existe autenticación DRF `ApiKey` en este repositorio.
- El aislamiento schema-per-tenant y los datos de negocio viven en `flowkron-operational-service`, no en esta base IAM compartida.
- La auditoría se escribe sincrónicamente con ORM; no hay pipeline asíncrono de auditoría.
- Celery está configurado, pero no hay tareas de negocio versionadas actualmente.
- `/health/` y `/healthz/` son liveness superficial; no verifican DB, Redis, migraciones ni signing keys.

## Mapa de código

| Ruta | Responsabilidad |
| --- | --- |
| `apps/accounts/` | login, perfil, tokens humanos y `/me` |
| `apps/tenants/` | Tenants, planes, miembros, invitaciones y runtime operacional |
| `apps/rbac/` | Permisos, roles y asignaciones |
| `apps/sessions/` | Sesiones y señales de riesgo |
| `apps/security/` | Email/password tokens, MFA, JWKS, service accounts y API keys |
| `apps/audit/` | AuditLog sincrónico |
| `apps/shared/` | Permisos DRF, errores, uploads, logging y correlación |
| `config/settings/` | Settings base/local/production |
| `docs/` | Documentación técnica y operativa mantenida |

Flujo usual: serializer valida entrada; view coordina HTTP; service contiene reglas reutilizables; model persiste. Parte de la lógica histórica aún vive en serializers/views: no documentes una arquitectura ideal como si ya estuviera implementada.

## Invariantes críticas

- `django.contrib.auth.User` es la identidad humana base y `UserProfile` su extensión 1:1.
- Login humano requiere usuario activo, correo verificado, membresía activa y tenant activo; si MFA está habilitado exige TOTP.
- El tenant solicitado debe coincidir con el claim `tenant_id` cuando el token ya lo contiene.
- Permiso efectivo = permisos de roles ∩ entitlements del plan/suscripción.
- Tokens de un solo uso, API keys y client secrets se almacenan hasheados; claves privadas administradas se cifran.
- `SIGNING_KEY_ENCRYPTION_KEY` debe permanecer estable: cambiarla impide descifrar claves privadas existentes.
- Las invitaciones, verificación de correo y recuperación dependen de SMTP; `APP_PUBLIC_URL` forma el enlace de invitación.
- Activar una suscripción llama sincrónicamente al servicio operacional y puede devolver 502 si este falla.

## Configuración relevante

No leas `.env` ni expongas secretos. Usa `.env.example` y `config/settings/base.py` como fuentes.


Flags de entrypoint: `GENERATE_JWT_KEYS`, `RUN_MIGRATIONS`, `RUN_SEEDS`, `RUN_COLLECTSTATIC`, `CREATE_SUPERUSER` y variables `DJANGO_SUPERUSER_*`.

## Autorización del agente

Permitido dentro del alcance solicitado: leer código/documentación, editar aplicación o docs, añadir pruebas y ejecutar checks locales no destructivos.

Requiere aprobación humana explícita: dependencias, CI/CD, Docker/infraestructura, nuevas migraciones, contratos públicos incompatibles, cambios de autenticación/autorización, despliegues o acciones destructivas.

No leer ni modificar: `.env`, llaves privadas, certificados, secretos, datos reales, `staticfiles/`, `__pycache__/` ni migraciones existentes. Nunca incluyas correos personales, contraseñas, tokens o client secrets en ejemplos.

## Comandos oficiales

```powershell
pip install -r requirements.txt
python scripts/generate_jwt_keys.py
python manage.py migrate
python manage.py seed_iam
python manage.py seed_iam_advanced
python manage.py runserver

python -m compileall -q apps config scripts manage.py
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
docker compose config
```

Para crear un superusuario usa valores provistos por variables de entorno, nunca credenciales copiadas de la documentación:

```powershell
python manage.py ensure_superuser --email $env:DJANGO_SUPERUSER_EMAIL --password $env:DJANGO_SUPERUSER_PASSWORD
```

## Validación proporcional

- Solo documentación: comprobar enlaces/rutas, buscar referencias obsoletas y revisar `git diff --check`; ejecutar Django checks si el runtime está disponible.
- Código Python: compileall, `manage.py check`, migraciones pendientes y pruebas relevantes.
- Contrato HTTP: además generar/revisar OpenAPI y actualizar `docs/API.md`.
- Docker/settings: además `docker compose config`; no levantar servicios ni tocar volúmenes sin que el alcance lo justifique.

La suite actual tiene 20 tests, pero no cubre exhaustivamente endpoints, aislamiento cross-tenant, refresh reuse, invitaciones ni aprovisionamiento operacional. No declares cobertura que no exista.

## Documentos canónicos

- [Índice](docs/README.md)
- [Arquitectura](docs/ARCHITECTURE.md)
- [API](docs/API.md)
- [Modelo de datos](docs/DATA_MODEL.md)
- [Seguridad](docs/SECURITY.md)
- [Despliegue](docs/DEPLOYMENT.md)
- [Operación y runbooks](docs/OPERATIONS.md)
- [Testing](docs/TESTING.md)

## Definición de terminado

El trabajo permanece dentro del alcance, no expone secretos, deja un diff claro, pasa las validaciones disponibles y mantiene sincronizados comportamiento, OpenAPI y documentación. Si una validación no pudo ejecutarse, indícalo sin afirmar éxito.
