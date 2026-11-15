# Seguridad y preparación productiva

## Secretos

`docker compose config` expande secretos; usar `--quiet`. También revisar logs, inspect, backups y shell history.

El init genera credenciales independientes por proyecto y las escribe en volúmenes internos. Conservar estos volúmenes junto a las bases de datos. El usuario inicial de laboratorio solo se aprovisiona en una base vacía, con debug y bind loopback.

## JWT y almacenamiento

Los montajes predeterminados separan las claves privada y pública. Auth guarda la privada. Operational y Agent Core montan el volumen público en solo lectura. Para conservar montajes antiguos y separar también las claves, configura `FLOWKRON_JWT_PUBLIC_MOUNT` con la ubicación de la clave pública.

La generación automática de claves puede invalidar sesiones si se pierde/regenera el directorio. Definir ciclo de vida, backup cifrado y rotación coordinada.

## Datos y exposición

PostgreSQL, Redis, las APIs y ambos frontends escuchan en loopback por defecto. El gateway de correo y Baileys permanecen en la red interna. Fuera de local:

- no publicar DB/Redis;
- colocar APIs/frontends detrás de ingress/reverse proxy HTTPS;
- restringir firewall, CORS y allowed hosts;
- aplicar autenticación/ACL a observabilidad y administración;
- cifrar backups y probar restores.



## Defaults no productivos

Antes de un ambiente real: configurar `DJANGO_DEBUG=False`, hosts permitidos, TLS y secretos privados adecuados. Revisar migraciones y bootstrap según el proceso del entorno. Probar correo con el proveedor elegido.

## Brechas de plataforma

Este Compose ofrece un entorno de un solo host. La infraestructura de producción debe definir TLS, proxy, rotación de secretos, backups, observabilidad y recuperación según el despliegue.

Las imágenes de infraestructura fijan versión mayor (`postgres:18`, `redis:7`), no digest/patch inmutable. Planificar actualizaciones y escaneo de vulnerabilidades.

## Producción

No desplegar el Compose local sin una arquitectura aprobada que resuelva las brechas anteriores. Un healthcheck verde no acredita seguridad, recuperación ni capacidad productiva.
