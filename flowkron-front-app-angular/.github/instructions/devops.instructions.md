---
applyTo: "**/{Dockerfile,docker-compose.yml,compose.yml,.github/workflows/**,infra/**}"
---

# Convenciones DevOps

- **Aprobación Obligatoria:** No modifique workflows de CI/CD, configuraciones de Nginx en `nginx.conf`, empaquetados en `Dockerfile` o arquitecturas de contenedores sin el consentimiento explícito del desarrollador humano.
- **Empaquetado de Producción:** La aplicación es compilada por Node.js y servida a través de un contenedor Nginx optimizado con Gzip.
- **Local Compose:** El archivo `docker-compose.yml` local expone la app en el puerto `8081` y cuenta con un perfil (`visual`) para lanzar el contenedor con Playwright para tests automatizados.
