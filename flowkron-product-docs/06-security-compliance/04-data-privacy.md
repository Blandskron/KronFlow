# Privacidad de datos: inventario técnico

**Versión:** 1.0
**Tipo:** Evidencia técnica
**Última verificación:** 2026-06-22

Este documento describe dónde puede existir información personal. Bases legales, plazos regulatorios, textos de consentimiento y atención formal de derechos pertenecen a revisión legal/producto, no se declaran aquí.

## Superficies de datos

| Superficie | Datos observados | Persistencia actual |
|---|---|---|
| IAM | identidad, correo, teléfono, membresía, MFA, sesiones | PostgreSQL compartido |
| Archivos IAM | medios o archivos asociados | bind mount `auth-media` en Compose local |
| Operacional | contactos, conversaciones, mensajes y eventos | esquema PostgreSQL por tenant |
| Ingesta WhatsApp | payload y metadatos del mensaje | API receptora; no existe gateway proveedor completo |
| Frontend app | tokens de sesión | `localStorage` del navegador |
| Landing | datos escritos en formularios | no se envían a backend actualmente |
| Terceros web | Google Identity Services y fuentes de Google | solicitudes desde el navegador |

IAM incluye entidades técnicas para solicitudes de derechos y registros de limpieza (`solicitudes_derechos` y `log_limpiezas`), pero su existencia no prueba un proceso legal u operacional completo.

## Controles y pendientes

- La separación operacional por esquema reduce mezcla accidental entre tenants, pero requiere disciplina de migraciones y pruebas de aislamiento.
- Debe definirse minimización, clasificación, cifrado, borrado y retención por tipo de dato.
- Los logs no deben incorporar tokens, secretos ni payloads personales completos.
- Cualquier transferencia a proveedores de IA será una arquitectura futura y requerirá evaluación antes de implementarse.
