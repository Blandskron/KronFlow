# Modelo de datos

## Convenciones

- Las tablas IAM usan prefijo `iam_`.
- Las entidades sensibles incluyen timestamps de auditoria cuando aplica.
- Los secretos nunca se almacenan en claro.
- Los tokens de un solo uso se guardan como hash.
- Las API keys se muestran solo una vez al crear o rotar.

## Identidad humana

### `auth_user`

Modelo nativo de Django. Contiene credenciales, flags de staff/superuser y datos base del usuario.

### `iam_user_profile`

Extension 1:1 de `auth_user`.

Campos principales:

- `user_id`
- `display_name`
- `phone`
- `avatar_url`
- `timezone`
- `locale`
- `email_verified_at`
- `account_activated_at`
- `initial_password_set_at`
- `onboarding_completed_at`
- `mfa_enabled`
- `mfa_confirmed_at`
- `created_at`
- `updated_at`

Invariantes:

- Todo usuario debe tener perfil.
- `mfa_enabled=True` requiere dispositivo confirmado.
- Login humano exige email verificado.
- Un usuario sin tenant activo puede tener sesion limitada con `onboarding_required=true`.
- `onboarding_completed_at` se marca al crear o aceptar el primer tenant/membership.

## Tenants

### `iam_tenant`

Representa una empresa cliente.

Campos principales:

- `slug`
- `name`
- `legal_name`
- `tax_id`
- `logo_url`
- `country`
- `status`
- `plan`
- `subscription_status`
- `subscription_provider`
- `subscription_external_id`
- `subscription_current_period_end`
- `created_by`
- `created_at`
- `updated_at`

Estados:

- `active`
- `suspended`
- `archived`

Planes:

- `free`
- `starter`
- `pro`
- `enterprise`

Estados de suscripcion:

- `free`
- `trialing`
- `active`
- `past_due`
- `canceled`
- `unpaid`

Regla de autorizacion:

- Los roles RBAC expresan lo que el usuario podria hacer dentro del tenant.
- Los entitlements de suscripcion expresan lo que el tenant tiene habilitado.
- Los permisos efectivos son la interseccion entre RBAC y entitlements.

### `iam_tenant_membership`

Relaciona usuarios con tenants.

Campos principales:

- `user_id`
- `tenant_id`
- `status`
- `invited_by`
- `joined_at`
- `revoked_at`
- `created_at`
- `updated_at`

Estados:

- `invited`
- `active`
- `suspended`
- `revoked`

Regla:

- Un usuario puede pertenecer a multiples tenants.
- Un usuario no puede tener membresia duplicada en el mismo tenant.

### `iam_tenant_invitation`

Gestiona invitaciones a tenants.

Campos principales:

- `tenant_id`
- `email`
- `token_hash`
- `role_code`
- `status`
- `invited_by`
- `accepted_by`
- `expires_at`
- `accepted_at`
- `rejected_at`
- `revoked_at`
- `created_at`

Estados:

- `pending`
- `accepted`
- `rejected`
- `expired`
- `revoked`

Reglas:

- El token se guarda solo como hash.
- La invitacion expirada o aceptada no puede reutilizarse.
- Un usuario existente debe autenticarse con el mismo email invitado para aceptarla.
- Un usuario nuevo puede activarse solo si posee un token valido.

### `iam_tenant_operational_runtime`

Proyección 1:1 del runtime administrado por el servicio operacional.

Campos principales:

- `tenant_id`
- `schema_name`
- `tenant_code`
- `plan`
- `status`
- `provisioned_at`
- `suspended_at`
- `last_sync_at`
- `last_error`
- `created_at`
- `updated_at`

Estados: `pending`, `active`, `suspended`, `cancelled`, `provision_failed`.

No contiene la ingest key; esta se entrega una sola vez desde el servicio operacional.

## Contacto publico

### `iam_contact_message`

Persiste mensajes enviados desde la landing publica.

Campos principales:

- `name`
- `email`
- `company`
- `phone`
- `message`
- `accept_terms`
- `status`
- `ip_address`
- `user_agent`
- `created_at`

Estados: `new`, `reviewed`, `archived`.

Reglas:

- El endpoint publico requiere CSRF.
- Los campos de texto rechazan HTML, caracteres de control y secuencias SQL de alto riesgo.
- La escritura usa ORM Django, sin SQL crudo.

## RBAC

### `iam_permission`

Permisos en formato `resource.action`.

Ejemplos:

- `users.read`
- `users.create`
- `roles.assign`
- `agents.create`
- `whatsapp.connect`
- `crm.manage`
- `audit.read`
- `auth.verify_token`
- `sessions.validate`
- `tenants.read`
- `api_keys.manage`
- `signing_keys.rotate`
- `service_accounts.manage`

### `iam_tenant_role`

Roles definidos por tenant.

Roles base:

- `TENANT_OWNER`
- `TENANT_ADMIN`
- `MANAGER`
- `VENDEDOR`
- `AGENT_SUPERVISOR`
- `AGENT_OPERATOR`
- `VIEWER`

### `iam_role_permission`

Relaciona roles con permisos.

### `iam_membership_role`

Relaciona memberships con roles.

## Sesiones

### `iam_user_session`

Registra sesiones por usuario y tenant. Durante onboarding inicial puede existir una sesion sin tenant/membership.

Campos principales:

- `user_id`
- `tenant_id`
- `membership_id`
- `ip_address`
- `user_agent`
- `status`
- `risk_score`
- `risk_flags`
- `expires_at`
- `revoked_at`
- `token_family`
- `last_refresh_at`
- `created_at`
- `updated_at`

Estados:

- `active`
- `revoked`
- `expired`
- `compromised`

Risk flags:

- `NEW_DEVICE`
- `DEVICE_CHANGED`
- `IP_CHANGED`
- `REFRESH_REUSE_DETECTED`

## Seguridad

### `iam_signing_key`

Administra claves RS256.

Campos:

- `kid`
- `algorithm`
- `public_key`
- `encrypted_private_key`
- `status`
- `created_at`
- `expires_at`
- `rotated_at`

Estados:

- `active`
- `inactive`
- `revoked`

Reglas:

- `kid` es obligatorio y unico.
- JWKS publica claves vigentes no revocadas.
- La rotacion marca claves activas como inactivas durante ventana de compatibilidad.

### `iam_service_account`

Identidad maquina-a-maquina.

Campos:

- `name`
- `client_id`
- `secret_hash`
- `scopes`
- `status`
- `expires_at`
- `last_used_at`
- `created_at`
- `updated_at`

### `iam_api_key`

API keys por tenant para integraciones externas.

Campos:

- `tenant_id`
- `name`
- `prefix`
- `key_hash`
- `scopes`
- `status`
- `expires_at`
- `last_used_at`
- `revoked_at`
- `created_by`
- `created_at`
- `updated_at`

Reglas:

- Nunca guardar key completa.
- Guardar solo hash.
- Mostrar key solo al crear o rotar.
- Revocar key anterior al rotar.

## MFA

### `iam_mfa_device`

Dispositivo TOTP por usuario.

### `iam_mfa_recovery_code`

Codigos de recuperacion hasheados.

## Tokens de un solo uso

### `iam_email_verification_token`

Token hasheado para verificacion de email.

### `iam_password_reset_token`

Token hasheado para recuperacion de password.

## Auditoria

### `iam_audit_log`

Eventos de seguridad.

Campos:

- `user_id`
- `tenant_id`
- `event`
- `ip_address`
- `user_agent`
- `correlation_id`
- `metadata`
- `created_at`

Eventos destacados:

- `user_created`
- `email_verification_sent`
- `email_verified`
- `account_activated`
- `login_success`
- `login_failed`
- `logout`
- `refresh`
- `password_reset_requested`
- `password_reset_completed`
- `tenant_created`
- `tenant_owner_assigned`
- `invitation_sent`
- `invitation_accepted`
- `invitation_expired`
- `invitation_revoked`
- `password_changed`
- `mfa`
- `role_changed`
- `member_role_changed`
- `member_removed`
- `member_changed`
- `session_revoked`
- `signing_key_rotated`
- `api_key_created`
- `api_key_revoked`
- `api_key_rotated`
- `service_account_created`
- `session_risk_detected`
- `session_compromised`
