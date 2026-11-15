# Seguridad

## Controles implementados

- Passwords con Argon2 como hasher preferido y validadores Django (mínimo 12, similitud, comunes y numéricos).
- django-axes para bloqueo por combinación IP/username y throttling DRF por usuario, anónimo y scopes sensibles.
- JWT RS256 con `aud=flowkron`, `iss=flowkron-auth-service`, access de 10 minutos y refresh de 14 días con rotación/blacklist de Simple JWT.
- RBAC tenantizado limitado por entitlements de suscripción.
- Tokens de correo/password, API keys y client secrets almacenados como SHA-256; claves privadas administradas cifradas con Fernet derivado de `SIGNING_KEY_ENCRYPTION_KEY`.
- CORS explícito, CSRF middleware, cookies seguras fuera de debug, HSTS/SSL redirect en settings de producción.
- El formulario publico de contacto exige token CSRF obtenido en `/api/v1/contact/csrf/` y enviado como `X-CSRFToken` a `/api/v1/contact/messages/`.
- Uploads limitados a JPEG/PNG/WebP, 3 MiB y reprocesados con Pillow.
- Auditoría sincrónica y logs JSON con correlación.

## Modelo de autorización

`HasTenantPermission` obtiene tenant desde `X-Tenant-ID`, query/body o claim. Si existe claim, rechaza un tenant diferente; exige membership activa y luego comprueba permiso efectivo. El permiso efectivo es:

```text
permisos de los roles de la membership ∩ entitlements del plan activo
```


## Familias de tokens

Hay dos emisores internos con material de firma distinto:

- JWT humanos: Simple JWT usa `JWT_PRIVATE_KEY(_PATH)` y `JWT_PUBLIC_KEY(_PATH)`.
- JWT de service account: se firman con la clave activa de `iam_signing_key` y llevan header `kid`.

`GET /api/v1/auth/jwks/` publica las signing keys vigentes de base de datos; no publica automáticamente la clave pública configurada para Simple JWT. Cada consumidor debe validar que su estrategia cubre la familia de token que recibe.

Claims humanos adicionales: `tenant_id`, `membership_id`, `session_id`, `roles`, `permissions`, `subscription`, `onboarding_required` y `amr`. Cuando `onboarding_required=true`, el token no representa contexto tenant y solo debe usarse para completar el onboarding inicial.

Claims de service account: `sub`, `typ=service_account`, `scopes`, `iat`, `exp`, `jti`, además de issuer/audience y `kid`.

## Introspection

`POST /api/v1/auth/introspect/` no es público anónimo en la práctica: el caller debe enviar un bearer token de service account activo con scope `auth.verify_token`; el token a inspeccionar va en el body. Para JWT humanos también comprueba que la sesión siga activa.

## Secretos y rotación

- El secreto de service account y la API key solo se devuelven al crear/rotar.
- `SIGNING_KEY_ENCRYPTION_KEY` debe ser fuerte, secreto y estable; su pérdida o cambio rompe el descifrado de claves privadas existentes.
- La rotación de signing key mantiene la anterior como `inactive` durante 14 días por defecto.
- El par de Simple JWT debe persistirse fuera de la imagen y rotarse con un procedimiento compatible para sus consumidores.

## Sesiones y riesgo

Al crear sesión se marcan `NEW_DEVICE`, `DEVICE_CHANGED` o `IP_CHANGED` comparando con la sesión previa. Existe `mark_refresh_reuse`, pero el flujo HTTP de refresh actual no lo invoca; por tanto no se debe afirmar detección automática de refresh reuse. Logout y cambio/reset de password revocan sesiones IAM, pero la validación JWT normal de Simple JWT no consulta `UserSession` en cada request; usa introspection o el endpoint de estado cuando se requiera revocación inmediata distribuida.

## Onboarding e invitaciones

- No existe registro publico abierto.
- Un usuario con email no verificado no puede completar onboarding ni operar endpoints tenantizados.
- `/api/v1/tenants/onboarding/` crea el primer tenant solo para usuarios verificados sin membership activa.
- El tenant debe conservar al menos un miembro activo con rol `TENANT_OWNER`; no se permite remover ni degradar al ultimo owner.
- Las invitaciones usan token aleatorio hasheado, expiracion, estado y un solo uso.
- Un usuario existente solo puede aceptar una invitacion si esta autenticado y su email coincide con el email invitado.
- Un usuario nuevo puede activarse solo mediante token de invitacion valido; ese flujo no equivale a registro publico.
- Los tokens de invitacion se envian por correo/enlace y no deben escribirse en logs.

## API keys: límite explícito

Este repositorio administra metadata, hash, scopes, revocación y rotación de API keys. No contiene una authentication class/middleware que acepte `Authorization: ApiKey`. El gateway o servicio consumidor debe implementar la validación runtime y sincronizar la revocación.

## Riesgos y brechas conocidas

- `/health/` y `/healthz/` son solo liveness.
- Introspection y client credentials están expuestos con `AllowAny` a nivel DRF y dependen de sus propias credenciales/throttling; protegerlos también en gateway.
- No hay cache headers explícitos para JWKS.
- Algunos endpoints tienen tests limitados; ver [TESTING.md](TESTING.md).
- La auditoría no es inmutable a nivel de base de datos y no tiene pipeline externo en este repositorio.
- El servicio auth usa DB compartida; el aislamiento físico multi-schema corresponde al servicio operacional.
- `OPERATIONAL_INTERNAL_TOKEN` tiene un default local inseguro y debe sobrescribirse en cualquier ambiente compartido/productivo.
- La proteccion XSS/SQLi del formulario de contacto combina validacion/rechazo de HTML y secuencias peligrosas con escape por defecto en consumidores y ORM parametrizado; no reemplaza WAF, CSP ni revisiones de payloads abusivos en gateway.

## Producción

Usa `config.settings.base` con `DJANGO_DEBUG=False`, HTTPS, secret manager, PostgreSQL/Redis privados, backups probados, MFA para administradores, alertas y acceso restringido a admin/Swagger. Consulta [OPERATIONS.md](OPERATIONS.md) para el checklist y [LEGAL_AND_ACCEPTABLE_USE.md](LEGAL_AND_ACCEPTABLE_USE.md) para pruebas de seguridad autorizadas.
