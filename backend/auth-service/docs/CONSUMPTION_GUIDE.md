# Guia de consumo del microservicio IAM

Este documento explica como deben consumir `flowkron-auth-service` los distintos tipos de clientes de la plataforma:

- frontend web/mobile
- microservicios internos
- integraciones externas por tenant

El objetivo es estandarizar autenticacion, autorizacion, manejo de tokens, seleccion de tenant, errores, seguridad y auditoria.

## Principios generales

- El frontend nunca decide permisos por si solo; solo adapta UI segun permisos entregados por el backend.
- Los microservicios internos deben validar JWT por JWKS o introspection.
- Las integraciones externas deben usar API keys tenantizadas con scopes minimos cuando el gateway o servicio consumidor implemente la validacion runtime; este repositorio solo administra esas keys.
- Ningun consumidor debe almacenar passwords.
- Ningun consumidor debe loguear access tokens, refresh tokens, API keys, client secrets o recovery codes.
- Toda llamada tenantizada debe incluir tenant activo.
- Todo consumidor debe manejar errores estandarizados.

## Ciclo de onboarding y suscripcion

El ciclo funcional esperado para frontend es:

Flujo vigente:

```text
1. Administrador crea usuario o el usuario llega por invitacion valida.
2. Usuario verifica email y define password inicial si corresponde.
3. Usuario hace login.
4. Si onboarding_required=true, frontend solicita nombre de empresa.
5. Frontend llama POST /api/v1/tenants/onboarding/.
6. Django crea tenant logico inicial con plan Free.
7. Django asigna membership activa y rol TENANT_OWNER.
8. Backend entrega nuevos tokens con tenant, roles y permisos efectivos limitados por suscripcion.
9. Frontend muestra estado Free y CTA de compra/upgrade si aplica.
10. Billing activa plan pagado en el tenant.
11. Usuario refresca sesion o vuelve a llamar /auth/me/.
12. Backend entrega permisos efectivos del rol owner habilitados por plan pagado.
13. Owner puede invitar miembros, asignar roles, crear API keys y operar IAM tenantizado.
```

El bloque historico siguiente queda solo como referencia de capacidades relacionadas con suscripcion y runtime operacional.

```text
2. Frontend solicita nombre de empresa.
3. Django crea tenant lógico inicial con plan Free.
4. Django llama síncrona o asíncronamente a FastAPI para aprovisionar el esquema físico.
5. FastAPI inicializa el esquema ("tenant_xxx") y genera la ingest_key y tenant_code.
6. Django asigna membership activa y rol TENANT_OWNER.
7. Backend entrega permisos efectivos limitados por suscripcion.
8. Frontend muestra estado Free, proporciona las claves de ingesta para un adaptador externo de WhatsApp, y muestra CTA de compra.
9. Billing activa plan pagado en el tenant.
10. Usuario refresca sesion o vuelve a llamar /auth/me/.
11. Backend entrega permisos efectivos del rol owner habilitados por plan pagado.
12. Owner puede invitar miembros, asignar roles, crear API keys y operar IAM tenantizado.
```

Regla central:

```text
permisos_efectivos = permisos_RBAC_del_usuario intersectados con entitlements_del_plan
```

Un usuario puede ser `TENANT_OWNER`, pero si el tenant esta en `plan=free` solo recibira entitlements de onboarding. Esto evita que el alta de cuenta equivalga automaticamente a acceso operacional completo.

Estados relevantes del tenant:

| Campo | Uso |
| --- | --- |
| `plan` | `free`, `starter`, `pro`, `enterprise` |
| `subscription_status` | `free`, `trialing`, `active`, `past_due`, `canceled`, `unpaid` |
| `subscription.requires_paid_plan` | Indica al frontend que debe mostrar compra/upgrade |
| `subscription.entitlements` | Capacidades habilitadas por plan |

Para planes pagados, el tenant debe quedar con `subscription_status=active` o `trialing`. Si queda `past_due`, `canceled` o `unpaid`, el backend no debe entregar permisos operacionales aunque el rol RBAC los tenga.

## URLs base

Local:

```text
http://127.0.0.1:8000
```

Docker:

```text
http://localhost:8000
```

API:

```text
/api/v1/
```

OpenAPI:

```text
/api/schema/
/api/docs/
```

## Formato estandar de respuesta

Exito:

```json
{
  "success": true,
  "status": {
    "code": 200,
    "message": "Request completed successfully"
  },
  "data": {},
  "meta": {
    "api_version": "v1",
    "service": "auth-service",
    "request_id": "req_uuid",
    "correlation_id": "corr_uuid",
    "timestamp": "2026-07-05T02:12:00Z"
  }
}
```

Error (Problem Details RFC 7807):

```json
{
  "type": "urn:flowkron:problem:auth-403-permission-denied",
  "title": "Forbidden",
  "status": 403,
  "detail": "Permiso tenant requerido.",
  "instance": "/api/v1/some-endpoint/",
  "error_code": "AUTH_403_PERMISSION_DENIED",
  "errors": [],
  "meta": {
    "api_version": "v1",
    "service": "auth-service",
    "request_id": "req_uuid",
    "correlation_id": "corr_uuid",
    "timestamp": "2026-07-05T02:12:00Z"
  }
}
```

## Consumo desde frontend web/mobile

### Responsabilidad del frontend

El frontend debe:

- enviar credenciales solo al auth service
- guardar access token en memoria o mecanismo seguro aprobado
- no guardar refresh token en storage inseguro
- enviar `Authorization: Bearer <access_token>`
- manejar expiracion de access token
- refrescar token cuando corresponda
- llamar `/auth/me/` al iniciar sesion o recargar aplicacion
- respetar tenant activo
- ocultar acciones sin permisos, pero sin confiar en esa ocultacion como seguridad
- forzar MFA cuando el backend lo indique

### Flujo recomendado de login

```text
1. Usuario ingresa email y password
2. Frontend llama POST /api/v1/auth/login/
3. Si MFA es requerido, frontend solicita codigo TOTP
4. Frontend repite login con mfa_code
5. Backend devuelve access, refresh, tenant_id, roles y permissions
6. Frontend guarda contexto de sesion
7. Frontend llama GET /api/v1/auth/me/
8. Frontend renderiza UI segun tenant, roles y permissions
```

### Flujo recomendado de alta manual

Flujo vigente:

```text
1. Administrador crea usuario desde admin/comando interno.
2. Backend envia token de verificacion.
3. Usuario confirma email en /api/v1/auth/email/confirm/; puede enviar new_password.
4. Usuario hace login.
5. Si onboarding_required=true, frontend pide nombre de empresa.
6. Frontend llama POST /api/v1/tenants/onboarding/.
7. Backend crea tenant Free, asigna TENANT_OWNER y emite tokens con tenant.
8. Frontend llama GET /api/v1/auth/me/.
9. Si subscription.requires_paid_plan=true, mostrar pantalla de seleccion/compra de plan.
```

### Login

Request:

```http
POST /api/v1/auth/login/
Content-Type: application/json
```

Body:

```json
{
  "email": "owner@example.com",
  "password": "a-very-safe-password-123",
  "tenant_id": 1,
  "mfa_code": "123456"
}
```

Response:

```json
{
  "success": true,
  "data": {
    "access": "<access_token>",
    "refresh": "<refresh_token>",
    "session_id": 10,
    "tenant_id": 1,
    "onboarding_required": false,
    "roles": ["TENANT_OWNER"],
    "permissions": ["tenants.read"],
    "subscription": {
      "plan": "free",
      "status": "free",
      "entitlements": ["tenants.read"],
      "current_period_end": null,
      "requires_paid_plan": true
    }
  }
}
```

### Obtener usuario actual

Request:

```http
GET /api/v1/auth/me/
Authorization: Bearer <access_token>
```

Response:

```json
{
  "success": true,
  "data": {
    "user": {},
    "tenant": {},
    "membership": {},
    "roles": ["TENANT_OWNER"],
    "permissions": ["tenants.read"],
    "subscription": {
      "plan": "free",
      "status": "free",
      "entitlements": ["tenants.read"],
      "current_period_end": null,
      "requires_paid_plan": true
    },
    "session": {
      "id": 10,
      "status": "active",
      "expires_at": "2026-06-20T00:00:00Z"
    }
  }
}
```

### Refresh token

Request:

```http
POST /api/v1/auth/refresh/
Content-Type: application/json
```

Body:

```json
{
  "refresh": "<refresh_token>"
}
```

Response:

```json
{
  "access": "<new_access_token>",
  "refresh": "<new_refresh_token>"
}
```

Reglas:

- si refresh falla, cerrar sesion local
- si backend indica token blacklisted o invalido, redirigir a login
- no reintentar indefinidamente

### Logout

Request:

```http
POST /api/v1/auth/logout/
Authorization: Bearer <access_token>
```

Despues de logout:

- borrar tokens locales
- limpiar tenant activo
- limpiar cache de usuario/permisos
- redirigir a login

### Logout global

Request:

```http
POST /api/v1/auth/logout-all/
Authorization: Bearer <access_token>
```

Uso:

- cambio de password
- sospecha de cuenta comprometida
- cierre de todas las sesiones desde UI de seguridad

### Manejo de permisos en UI

El frontend puede usar `permissions` para mostrar u ocultar acciones.

Ejemplo:

```text
users.read       -> mostrar lista de usuarios
users.create     -> mostrar boton crear usuario
roles.assign     -> mostrar asignacion de roles
audit.read       -> mostrar auditoria
api_keys.manage  -> mostrar API keys del tenant
```

Importante:

- ocultar botones no es seguridad
- el backend siempre valida permisos
- `permissions` ya viene filtrado por suscripcion
- si una accion devuelve `PERMISSION_DENIED`, la UI debe mostrar mensaje controlado

### Manejo de tenant activo

El tenant activo viene en:

- login response
- `/auth/me/`
- claims del token

Para endpoints de administración e identidad (Django), enviar:

```http
X-Tenant-ID: <tenant_id>
```

o `tenant_id` como query param si el endpoint lo admite.

Para endpoints operacionales (FastAPI - leads, conversaciones, mensajes, agentes):
El cliente simplemente envía el encabezado `Authorization: Bearer <access_token>`. El backend operacional de FastAPI extrae automáticamente el `tenant_id` y `tenant_slug` de los claims del JWT firmados con RS256, resolviendo el esquema PostgreSQL correspondiente (`tenant_xxx`) sin necesidad de enviar encabezados adicionales de tenant.

### MFA en frontend

Flujo setup:

```text
1. POST /api/v1/auth/mfa/setup/
2. Mostrar QR basado en otpauth_uri
3. Usuario ingresa codigo TOTP
4. POST /api/v1/auth/mfa/confirm/
5. Mostrar recovery codes una sola vez
```

El frontend debe advertir:

- guardar recovery codes de forma segura
- no se volveran a mostrar
- acciones criticas pueden requerir MFA

### Errores comunes para frontend

| Code | Accion UI recomendada |
| --- | --- |
| `AUTH_INVALID_CREDENTIALS` | Mostrar credenciales invalidas |
| `AUTH_EMAIL_NOT_VERIFIED` | Mostrar opcion reenviar email |
| `MFA_REQUIRED` | Mostrar pantalla TOTP |
| `MFA_INVALID_CODE` | Pedir nuevo codigo |
| `ONBOARDING_ALREADY_COMPLETED` | Redirigir a selector/contexto tenant |
| `onboarding_required=true` | Mostrar onboarding obligatorio de empresa |
| `TENANT_ACCESS_DENIED` | Mostrar selector de tenant o acceso denegado |
| `PERMISSION_DENIED` | Ocultar accion o mostrar mensaje controlado |
| `TOKEN_NOT_VALID` | Cerrar sesion local |

## Consumo desde microservicios internos

Los microservicios internos tienen dos patrones:

- validar tokens de usuario recibidos desde frontend
- obtener tokens propios con client credentials

## Validar tokens de usuario

Los access tokens humanos son emitidos por Simple JWT con el par `JWT_PRIVATE_KEY`/`JWT_PUBLIC_KEY`. El JWKS de `/api/v1/auth/jwks/` publica las claves administradas en `iam_signing_key`, usadas por service accounts, y no incorpora automáticamente la clave de Simple JWT.

Por tanto, un microservicio debe recibir de forma segura la clave pública humana configurada o usar introspection autorizada. No debe asumir que el JWT humano trae `kid` resoluble en el JWKS actual.

Validaciones mínimas:

- firma RS256 con la clave pública de la familia correcta
- `iss=flowkron-auth-service`
- `aud=flowkron`
- `exp`
- tenant y permisos requeridos por la operación
- no aceptar `alg=none`
- no aceptar tokens sin `iss` o `aud`
- validar permisos en cada microservicio

### Claims esperados en tokens humanos

```json
{
  "user_id": 1,
  "tenant_id": "1",
  "membership_id": "1",
  "session_id": "10",
  "roles": ["TENANT_OWNER"],
  "permissions": ["users.read", "audit.read"],
  "amr": "pwd",
  "iss": "flowkron-auth-service",
  "aud": "flowkron"
}
```

## Validar tokens por introspection

Endpoint:

```http
POST /api/v1/auth/introspect/
Authorization: Bearer <service-account-token-con-auth.verify_token>
Content-Type: application/json
```

Body:

```json
{
  "token": "<jwt>"
}
```

Response:

```json
{
  "success": true,
  "data": {
    "active": true,
    "claims": {}
  }
}
```

Usar introspection cuando:

- se necesita validar estado actual de sesion
- se sospecha token revocado
- se requiere comprobar la sesión además de la firma local
- la accion es critica

Introspection agrega dependencia runtime, pero comprueba el estado de la sesión humana. No se puede invocar anónimamente: el caller debe ser una service account con scope `auth.verify_token`.

## Client credentials para microservicios

Endpoint:

```http
POST /api/v1/auth/client-credentials/
```

Body:

```json
{
  "client_id": "svc_xxx",
  "client_secret": "secret",
  "scopes": ["users.read", "sessions.validate"]
}
```

Response:

```json
{
  "success": true,
  "data": {
    "access_token": "<jwt>",
    "token_type": "Bearer",
    "expires_in": 600
  }
}
```

### Scopes internos

| Scope | Uso |
| --- | --- |
| `auth.verify_token` | Validar tokens |
| `users.read` | Consultar usuarios |
| `sessions.validate` | Validar sesiones |
| `tenants.read` | Consultar tenants |

Reglas:

- pedir solo scopes necesarios
- cachear token hasta antes de expirar
- rotar `client_secret` periodicamente
- no compartir service accounts entre servicios sin necesidad

### Claims esperados en service account token

```json
{
  "iss": "flowkron-auth-service",
  "aud": "flowkron",
  "sub": "svc_xxx",
  "typ": "service_account",
  "scopes": ["users.read"],
  "iat": 1780000000,
  "exp": 1780000600,
  "jti": "random"
}
```

## Consumo desde integraciones externas

Las integraciones externas deben usar API keys por tenant.

## Crear API key

Endpoint:

```http
POST /api/v1/security/api-keys/
Authorization: Bearer <token-mfa>
X-Tenant-ID: <tenant_id>
```

Body:

```json
{
  "name": "Zapier production",
  "scopes": ["users.read"],
  "expires_at": "2026-12-31T23:59:59Z"
}
```

Response:

```json
{
  "success": true,
  "data": {
    "id": 1,
    "name": "Zapier production",
    "prefix": "flowkron_abc123",
    "scopes": ["users.read"],
    "status": "active",
    "key": "flowkron_full_key_visible_once"
  }
}
```

Importante:

- `key` solo se devuelve al crear o rotar
- el backend almacena solo hash
- el consumidor externo debe guardarla en vault o secret manager

## Listar API keys

```http
GET /api/v1/security/api-keys/?tenant_id=1
Authorization: Bearer <token-mfa>
```

La lista devuelve metadata, nunca la key completa.

## Revocar API key

```http
POST /api/v1/security/api-keys/{id}/revoke/
Authorization: Bearer <token-mfa>
X-Tenant-ID: <tenant_id>
```

## Rotar API key

```http
POST /api/v1/security/api-keys/{id}/rotate/
Authorization: Bearer <token-mfa>
X-Tenant-ID: <tenant_id>
```

La key anterior queda revocada y se entrega una nueva key una sola vez.

## Cómo debería llamar una integración externa

Patrón que debe definir el gateway o servicio consumidor (no está implementado en este repositorio):

```http
Authorization: ApiKey <api_key>
X-Tenant-ID: <tenant_id>
```

Nota:

El modelo y endpoints administrativos de API keys estan implementados. La autenticacion runtime por `Authorization: ApiKey` debe implementarse en los endpoints de negocio que consuman esas API keys o en un middleware/gateway comun.

## Seguridad para integraciones externas

Las integraciones deben:

- guardar API keys en secret manager
- rotar keys periodicamente
- usar scopes minimos
- no compartir keys entre ambientes
- no usar keys productivas en desarrollo
- reportar exposiciones inmediatamente
- respetar rate limits

## Matriz de consumidores

| Consumidor | Credencial | Token | Validacion | Tenant |
| --- | --- | --- | --- | --- |
| Frontend web/mobile | email/password + MFA | JWT usuario | auth service emite, servicios validan | tenant activo |
| Microservicio interno con usuario delegado | JWT usuario recibido | JWT usuario | JWKS o introspection | claim `tenant_id` |
| Microservicio interno propio | client_id/client_secret | JWT service account | JWKS o introspection | no siempre aplica |
| Integracion externa | API key tenant | API key | hash/middleware/gateway | `X-Tenant-ID` |

## Buenas practicas de clientes

### Frontend

- usar interceptores HTTP para adjuntar access token
- refrescar token de forma controlada
- evitar multiples refresh simultaneos
- limpiar sesion en 401 definitivo
- nunca guardar secrets machine-to-machine

### Microservicios

- validar `iss`, `aud`, `exp`, `kid`
- cachear JWKS
- validar scopes/permisos localmente
- usar introspection en acciones criticas
- propagar `X-Correlation-ID`

### Integraciones externas

- usar HTTPS siempre
- almacenar API key en vault
- rotar API key
- monitorear 401/403
- enviar correlation ID si se entrega

## Codigos HTTP esperados

| HTTP | Significado |
| --- | --- |
| 200 | Operacion exitosa |
| 201 | Recurso creado |
| 400 | Request invalido |
| 401 | No autenticado o token invalido |
| 403 | Sin permiso |
| 404 | Recurso no encontrado o no accesible |
| 429 | Rate limit |
| 500 | Error interno |

## Correlation IDs

Todos los consumidores deberian enviar:

```http
X-Correlation-ID: <uuid>
```

El servicio responde:

```http
X-Request-ID: <uuid>
X-Correlation-ID: <uuid>
```

Esto permite trazar flujos entre frontend, auth service y otros microservicios.

## Checklist de integracion

Antes de conectar un consumidor:

- [ ] Definir tipo de consumidor
- [ ] Definir credencial requerida
- [ ] Definir scopes o permisos minimos
- [ ] Definir tenant requerido
- [ ] Definir estrategia de refresh o rotacion
- [ ] Definir almacenamiento seguro de secretos
- [ ] Definir manejo de 401/403/429
- [ ] Definir correlation ID
- [ ] Probar en ambiente no productivo
- [ ] Validar audit logs esperados
