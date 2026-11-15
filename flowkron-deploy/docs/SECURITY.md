# Seguridad y preparación productiva

## Secretos



`docker compose config` expande secretos; usar `--quiet`. También revisar logs, inspect, backups y shell history.

## JWT y bind mounts

Auth tiene acceso RW al directorio completo de claves; operational lo monta RO, pero puede leer todos los archivos del directorio, incluida la privada si está presente. El montaje RO impide escribir, no limita qué archivos puede leer. Para producción conviene entregar únicamente la clave pública a operational mediante secret/archivo dedicado y proteger permisos del host.

La generación automática de claves puede invalidar sesiones si se pierde/regenera el directorio. Definir ciclo de vida, backup cifrado y rotación coordinada.

## Datos y exposición

PostgreSQL, Redis, ambas APIs y ambos frontends se publican en todas las interfaces del host por defecto. Una red bridge no protege esos puertos. Fuera de local:

- no publicar DB/Redis;
- colocar APIs/frontends detrás de ingress/reverse proxy HTTPS;
- restringir firewall, CORS y allowed hosts;
- aplicar autenticación/ACL a observabilidad y administración;
- cifrar backups y probar restores.



## Defaults no productivos

Antes de un ambiente real: `DJANGO_DEBUG=False`, desactivar creación de superusuario/seeds/generación automática de claves según el proceso, revisar migraciones como job controlado, usar SMTP real administrado y eliminar defaults personales.

## Brechas de plataforma

Este repositorio no define TLS, reverse proxy, rate limiting de borde, Docker secrets, backups, restore, resource limits, logging centralizado, métricas/alertas, rolling update, alta disponibilidad ni separación de redes. `container_name` fijo y volúmenes locales dificultan escalado/multi-host.

Las imágenes de infraestructura fijan versión mayor (`postgres:18`, `redis:7`), no digest/patch inmutable. Planificar actualizaciones y escaneo de vulnerabilidades.

## Producción

No desplegar el Compose local sin una arquitectura aprobada que resuelva las brechas anteriores. Un healthcheck verde no acredita seguridad, recuperación ni capacidad productiva.
