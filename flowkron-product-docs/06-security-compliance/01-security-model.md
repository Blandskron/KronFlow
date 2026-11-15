# Modelo técnico de seguridad

**Versión:** 1.0
**Tipo:** Estado actual y brechas
**Última verificación:** 2026-06-22

## Alcance

Este documento registra controles observables en los repositorios. No constituye una certificación ni reemplaza decisiones legales o de riesgo.

## Controles implementados

- `flowkron-auth-service` centraliza identidad, emite JWT RS256 y aplica validaciones, permisos y throttling en sus endpoints.
- `flowkron-operational-service` valida JWT con la clave pública de IAM, usa un token interno para aprovisionamiento y separa datos mediante un esquema PostgreSQL por tenant.
- Las contraseñas se gestionan con Django; existen verificación de correo, recuperación de contraseña, MFA TOTP y acceso con Google.
- Los secretos principales se reciben mediante variables de entorno y las claves JWT se montan como archivos entre servicios.
- Los frontends productivos se sirven como archivos estáticos desde Nginx y los servicios poseen health checks en Docker Compose.

## Brechas verificadas

- No existe API gateway, reverse proxy global ni terminación TLS en el repositorio de despliegue.
- Los seis contenedores publican puertos al host; PostgreSQL y Redis también quedan expuestos en la configuración local.
- Los routers operacionales autentican al usuario, pero no aplican todavía autorización granular por rol o permiso.
- El límite del endpoint de ingesta operacional vive en memoria del proceso; no es distribuido.
- La aplicación Angular conserva tokens en `localStorage`, aumentando el impacto potencial de una vulnerabilidad XSS.
- Nginx no configura un conjunto explícito de cabeceras de seguridad.
- No hay pipeline automatizado de análisis de dependencias, secretos, SAST, DAST o imágenes.
- No hay monitoreo, alertas, backups ni pruebas de restauración implementadas.

## Prioridades técnicas

1. Definir y aplicar autorización operacional por permisos efectivos.
2. Diseñar el modelo de confianza y revocación JWT entre servicios.
3. Incorporar proxy/TLS, segmentación de puertos y cabeceras de seguridad para entornos no locales.
4. Añadir controles de seguridad automatizados en CI antes de declarar preparación productiva.
5. Implementar observabilidad, respaldo y restauración verificable.

## Fuentes canónicas

- `../flowkron-auth-service/docs/SECURITY.md`
- `../flowkron-operational-service/docs/SECURITY.md`
- `../flowkron-front-app-angular/docs/SECURITY.md`
- `../flowkron-front-landing-angular/docs/SECURITY.md`
- `../flowkron-deploy/docs/SECURITY.md`
