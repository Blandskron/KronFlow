# Infraestructura

Versión: 1.2
Tipo: estado actual + brechas
Estado: `PARTIAL`
Última verificación técnica: 2026-07-23

## Implementación actual

La única infraestructura reproducible versionada es Docker Compose local:

- PostgreSQL 18 y Redis 7;
- Auth, Operational y Agent Core;
- Landing y App con Nginx;
- red bridge, healthchecks y persistencia local.


## Persistencia

- PostgreSQL y Redis usan named volumes.
- Auth monta claves JWT y media.
- Operational y Agent Core leen la clave pública.

## Exposición

El stack publica servicios al host y usa HTTP. Está orientado a desarrollo/integración; no constituye una red productiva segura.

## No implementado

- infraestructura cloud desplegable;
- ingress, WAF o TLS de borde;
- alta disponibilidad/autoscaling;
- secretos administrados;
- observabilidad central;
- backups y restauración;
- CDN;
- registro de imágenes y CI/CD.
