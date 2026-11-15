---
applyTo: "**/{Dockerfile,docker-compose.yml,compose.yml,.github/workflows/**,infra/**}"
---

# Convenciones DevOps

- **Aprobación Obligatoria:** No modifiques archivos de CI/CD, configuraciones de infraestructura en Docker o workflows de GitHub Actions sin aprobación humana explícita.
- **Seguridad en Docker:**
  - La imagen base recomendada es `python:3.13-slim`.
  - Asegúrate de no guardar secretos duros, contraseñas o archivos `.env` reales dentro del contenedor o imágenes Docker.
- **Entornos:**
  - El archivo `docker-compose.yml` local debe servir para levantar y probar el entorno local completo.
  - Asegúrate de que las llaves JWT locales (`keys/jwt_private.pem` y `keys/jwt_public.pem`) se generen mediante el script y no se guarden en repositorios públicos.
- **Validación:**
  - Ejecuta `docker compose config` tras realizar cualquier cambio en el compose para comprobar su sintaxis.
