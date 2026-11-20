# API y contratos

Base local: `http://127.0.0.1:8000`. OpenAPI: `/api/schema/`; Swagger: `/api/docs/`. Este inventario describe rutas y autorización; Swagger es la referencia de campos exactos.

## Convenciones

Todo JSON bajo `/api/v1/*` usa el contrato compartido.

Exito:

```json
{
  "success": true,
  "status": {"code": 200, "message": "Request completed successfully"},
  "data": {},
  "meta": {
    "api_version": "v1",
    "service": "auth-service",
    "request_id": "req",
    "correlation_id": "corr",
    "timestamp": "2026-06-23T17:30:00Z"
  }
}
```

Error:

```json
{
  "type": "urn:flowkron:problem:auth-403-permission-denied",
  "title": "Forbidden",
  "status": 403,
  "detail": "Permiso tenant requerido.",
  "instance": "/api/v1/example/",
  "error_code": "AUTH_403_PERMISSION_DENIED",
  "errors": [],
  "meta": {
    "api_version": "v1",
    "service": "auth-service",
    "request_id": "req",
    "correlation_id": "corr",
    "timestamp": "2026-06-23T17:30:00Z"
  }
}
```

Un middleware contractual envuelve JSON bajo `/api/v1/*`, incluyendo vistas nativas de Simple JWT. Recursos tenantizados aceptan `X-Tenant-ID`; algunos tambien query/body. Si el JWT contiene `tenant_id`, debe coincidir.
## Auth humano y perfil

| Método y ruta | Auth | Propósito |
| --- | --- | --- |
| `GET /api/v1/auth/options/` | Pública | Indica si hay registro público y entrega el ID público y el desafío para Google |
| `POST /api/v1/auth/signup/` | Pública | Solicita por correo un enlace temporal para una cuenta nueva |
| `POST /api/v1/auth/signup/complete/` | Pública | Valida el enlace y la contraseña antes de crear la cuenta verificada |
| `POST /api/v1/auth/google/` | Pública | Valida la credencial de Google y el desafío de un solo uso, aplica MFA y emite una sesión de Flowkron |
| `POST /api/v1/auth/login/` | Pública | Emite access/refresh y crea sesión; admite `tenant_id` y `mfa_code`; si no hay tenant devuelve `onboarding_required=true` |
| `POST /api/v1/auth/refresh/` | Refresh token | Rota refresh y reconstruye claims del access si membership/sesión siguen activas |
| `POST /api/v1/auth/verify/` | Pública | Verifica JWT según Simple JWT |
| `GET /api/v1/auth/me/` | Bearer humano | Usuario, tenant, membership, roles, permisos, suscripción y sesión |
| `PATCH /api/v1/auth/profile/` | Bearer humano | Actualiza perfil y nombre/apellido |
| `POST /api/v1/auth/profile/avatar/` | Bearer humano, multipart | Guarda avatar JPEG/PNG/WebP |
| `POST /api/v1/auth/logout/` | Bearer humano | Revoca sesión actual en `UserSession` |
| `POST /api/v1/auth/logout-all/` | Bearer humano | Revoca sesiones activas del usuario |
| `POST /api/v1/auth/password/change/` | Bearer humano | Cambia password y revoca sesiones |
| `POST /api/v1/auth/password/initial-set/` | Bearer humano | Define password inicial y revoca sesiones |
| `POST /api/v1/auth/password/forgot/` | Pública | Envía código sin revelar si existe el usuario |
| `POST /api/v1/auth/password/reset/` | Pública | Consume código, cambia password y revoca sesiones |
| `POST /api/v1/auth/email/resend/` | Bearer humano | Reenvía verificación |
| `POST /api/v1/auth/email/confirm/` | Pública | Consume token de verificación; puede recibir `new_password` |
| `POST /api/v1/auth/mfa/setup/` | Bearer humano | Entrega secret y `otpauth_uri` |
| `POST /api/v1/auth/mfa/confirm/` | Bearer humano | Confirma TOTP y entrega recovery codes una vez |
| `POST /api/v1/auth/mfa/verify/` | Bearer humano | Comprueba un código TOTP |
| `GET /api/v1/auth/jwks/` | Pública | Signing keys DB vigentes; ver advertencia en `SECURITY.md` |

Con `AUTH_SELF_SIGNUP_ENABLED=True`, una cuenta nueva puede registrarse mediante un enlace de correo o una identidad de Google. La cuenta nueva llega al onboarding sin pertenecer a un tenant. El registro por correo usa `APP_PUBLIC_URL` para crear un enlace a `/registrarse#token=...` con dos horas de vigencia. Google identifica cada cuenta por el claim `sub`. Si el correo corresponde a una cuenta existente de Flowkron, esa cuenta requiere su método de acceso original.

Login recibe `email`, `password`, `tenant_id?`, `mfa_code?`. Los JWT humanos agregan `tenant_id`, `membership_id`, `session_id`, `roles`, `permissions`, `subscription`, `onboarding_required` y `amr`.

El registro de empresa aprovisiona su esquema operativo. El acceso se rige por la membresía, el rol y el estado de la empresa.

### Vincular WhatsApp

Las acciones sobre `/api/v1/tenants/{id}/whatsapp/` requieren una sesión de la empresa con permiso `whatsapp.connect`. `GET` devuelve el estado, el diagnóstico y el QR PNG si está pendiente y vigente. `POST` inicia el vínculo o reintenta la conexión. `DELETE` desconecta y elimina las credenciales locales de esa sesión. Las respuestas que incluyen el estado llevan `Cache-Control: no-store`.

`diagnostics` incluye la hora de la última transición, hasta ocho transiciones recientes, la última conexión, una causa normalizada, intentos realizados, próximo intento y próxima acción. IAM valida los campos y omite los datos de transporte ajenos al contrato. El QR requiere una fecha de vencimiento futura, por lo que el conector debe actualizarse antes de validar un vínculo nuevo desde el CRM actualizado.


| Método y ruta | Auth | Propósito |
| --- | --- | --- |
| `POST /api/v1/auth/client-credentials/` | `client_id`/`client_secret` en body | Emite JWT de service account por 600 s |
| `POST /api/v1/auth/introspect/` | Bearer service account con `auth.verify_token` | Inspecciona el token enviado en body |

Introspection devuelve 401 si falta/invalidan credenciales del caller y 403 si el caller no es service account o no tiene el scope.

## Contacto publico

La landing publica usa estos endpoints sin bearer token:

| Metodo y ruta | Auth | Proposito |
| --- | --- | --- |
| `GET /api/v1/contact/csrf/` | Publica | Emite `csrfToken` y setea cookie CSRF para el navegador |
| `POST /api/v1/contact/messages/` | Publica + CSRF | Persiste un mensaje de contacto |

`POST /api/v1/contact/messages/` requiere header `X-CSRFToken` con el token obtenido desde `/csrf/` y cookies habilitadas. Recibe `name`, `email`, `company?`, `phone?`, `message` y `accept_terms=true`. El backend valida largos, email, formato telefonico, aceptacion legal y rechaza HTML, caracteres de control y secuencias SQL de alto riesgo; la persistencia se hace con ORM, sin SQL crudo.

## Tenants

Todas las rutas bajo `/api/v1/tenants/` requieren bearer salvo preview/reject de invitación. Accept puede ser público solo cuando el token crea una cuenta nueva; si el usuario ya existe debe estar autenticado y su email debe coincidir con el email invitado.

| Método y ruta | Requisito adicional |
| --- | --- |
| `GET`, `POST /api/v1/tenants/` | Lista tenants del usuario / crea tenant Free |
| `POST /api/v1/tenants/onboarding/` | Bearer humano verificado sin tenant; crea tenant, asigna owner y devuelve tokens con tenant |
| `GET /api/v1/tenants/{id}/` | `tenants.read` |
| `PUT`, `PATCH`, `DELETE /api/v1/tenants/{id}/` | `tenants.manage` |
| `POST /api/v1/tenants/{id}/suspend/` o `activate/` | `tenants.manage` |
| `POST /api/v1/tenants/{id}/logo/` | `tenants.manage`, multipart |
| `GET`, `POST /api/v1/tenants/{id}/members/` | `members.manage` |
| `PATCH`, `DELETE /api/v1/tenants/{id}/members/{membership_id}/` | `members.manage` |
| `POST /api/v1/tenants/{id}/invite/` | `members.manage` |
| `GET /api/v1/tenants/{id}/invitations/` | `members.manage` |
| `POST /api/v1/tenants/{id}/invitations/{invitation_id}/revoke/` | `members.manage` |
| `GET /api/v1/tenants/invitations/preview/?token=...` | Pública |
| `POST /api/v1/tenants/invitations/accept/` | Token en body; usuario existente autenticado o password para cuenta nueva invitada |
| `POST /api/v1/tenants/invitations/reject/` | Pública, token en body |
| `GET /api/v1/tenants/{id}/runtime/` | `tenants.read` |
| `POST /api/v1/tenants/{id}/runtime/provision/` | `tenants.manage`; llama al servicio operacional |
| `POST /api/v1/tenants/{id}/runtime/rotate-ingest-key/` | `tenants.manage`; devuelve key una vez |
| `POST /api/v1/tenants/{id}/subscription/activate/` | `tenants.manage`; persiste plan y aprovisiona runtime |

`plan` y `subscription_*` son read-only en el serializer normal. Los endpoints operacionales pueden devolver 502 por dependencia externa.

Reglas importantes:

- No se crea tenant en onboarding si el email no esta verificado.
- El tenant debe conservar al menos un miembro activo con rol `TENANT_OWNER`.
- Cambiar roles o remover miembros requiere `members.manage`.
- Las invitaciones son tokenizadas, expiran, se aceptan una sola vez y pueden revocarse.

## RBAC, sesiones y auditoría

| Método y ruta | Requisito |
| --- | --- |
| `GET /api/v1/rbac/permissions/` | Bearer humano |
| CRUD `/api/v1/rbac/roles/` | `roles.assign` y tenant coincidente |
| `POST /api/v1/rbac/roles/{id}/permissions/` | `roles.assign` |
| `POST /api/v1/rbac/membership-roles/assign/` | `roles.assign` |
| `GET /api/v1/sessions/` y `/{id}/` | Solo sesiones del usuario autenticado |
| `POST /api/v1/sessions/{id}/revoke/` | Solo sesión propia |
| `GET /api/v1/sessions/status/` | Estado de la sesión del claim actual |
| `GET /api/v1/audit/?tenant_id=...` y `/{id}/` | `audit.read` |

## Seguridad administrativa

| Método y ruta | Requisito | Propósito |
| --- | --- | --- |
| `GET /api/v1/security/api-keys/?tenant_id=...` | `api_keys.manage` + MFA | Lista las API keys de un tenant |
| `POST /api/v1/security/api-keys/` | `api_keys.manage` + MFA | Crea una nueva API key para el tenant (devuelve key en claro una vez) |
| `GET /api/v1/security/api-keys/{id}/` | `api_keys.manage` + MFA | Obtiene detalles de una API key específica |
| `PUT /api/v1/security/api-keys/{id}/` | `api_keys.manage` + MFA | Actualización completa de la API key |
| `PATCH /api/v1/security/api-keys/{id}/` | `api_keys.manage` + MFA | Actualización parcial de la API key |
| `DELETE /api/v1/security/api-keys/{id}/` | `api_keys.manage` + MFA | Elimina de forma lógica/física la API key |
| `POST /api/v1/security/api-keys/{id}/revoke/` | `api_keys.manage` + MFA | Revoca una API key marcando su estado como `revoked` |
| `POST /api/v1/security/api-keys/{id}/rotate/` | `api_keys.manage` + MFA | Rota la API key (invalida la antigua, devuelve una nueva key en claro) |
| `GET /api/v1/security/service-accounts/` | Administrador de plataforma + MFA | Lista las service accounts registradas |
| `GET /api/v1/security/service-accounts/{id}/` | Administrador de plataforma + MFA | Obtiene una service account específica |
| `POST /api/v1/security/service-accounts/` | Administrador de plataforma + MFA | Crea una nueva service account (devuelve client_secret una vez) |
| `PUT /api/v1/security/service-accounts/{id}/` | Administrador de plataforma + MFA | Actualización completa de la service account |
| `PATCH /api/v1/security/service-accounts/{id}/` | Administrador de plataforma + MFA | Actualización parcial de la service account |
| `DELETE /api/v1/security/service-accounts/{id}/` | Administrador de plataforma + MFA | Elimina una service account |
| `GET /api/v1/security/signing-keys/` | Administrador de plataforma + MFA | Lista las signing keys (RS256) |
| `GET /api/v1/security/signing-keys/{id}/` | Administrador de plataforma + MFA | Obtiene detalles de una signing key específica |
| `POST /api/v1/security/signing-keys/rotate/` | Administrador de plataforma + MFA | Rota la firma principal generando una nueva clave activa |

El repositorio no implementa autenticación runtime con esas API keys.

## Códigos y trazabilidad

Usa 200/201 para éxito, 400 validación, 401 autenticación, 403 autorización, 404 recurso no visible, 429 throttle, 502 dependencia operacional y 500 fallo no controlado. Envía `X-Correlation-ID`; la respuesta incluye `X-Request-ID` y `X-Correlation-ID`.
