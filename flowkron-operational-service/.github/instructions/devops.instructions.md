---
applyTo: "**/{Dockerfile,docker-compose.yml,compose.yml,.github/workflows/**,infra/**}"
---

# Convenciones DevOps

- **Aprobación Obligatoria:** No modifiques workflows de CI/CD, configuraciones de infraestructura en Docker o archivos de despliegue sin aprobación humana explícita.
- **Seguridad en Docker:** No guardes secretos reales ni archivos `.env` en las imágenes de producción.
- **Compose local:** El `docker-compose.yml` local debe permitir levantar la app FastAPI conectándose a la base de datos PostgreSQL compartida.
