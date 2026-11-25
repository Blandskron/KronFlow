---
applyTo: "**/{Dockerfile,docker-compose.yml,compose.yml,compose/*.yml,.env.example}"
---

# Convenciones DevOps

- Mantén el root como agregador y los servicios en `compose/`.
- Usa nombres `flowkron-*`, imágenes versionadas y `restart: unless-stopped` cuando corresponda.
- Conecta servicios a `flowkron-network`; justifica redes adicionales y exposición al host.
- Todo `depends_on: condition: service_healthy` requiere un healthcheck útil, pero no sustituye retry de aplicación.
- Usa `${VAR:?mensaje}` para secretos obligatorios y placeholders inocuos en `.env.example`.
- Distingue named volumes de bind mounts y exige plan de backup/restore para datos/claves.
- Valida con `docker compose config --quiet`; nunca publiques la salida resuelta.
- No presentes el Compose local como producción sin hardening documentado.
