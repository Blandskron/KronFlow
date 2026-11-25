---
applyTo: "**/{Dockerfile,docker-compose.yml,compose.yml,.github/workflows/**,infra/**}"
---

# Convenciones DevOps

- **Aprobación Obligatoria:** No modifique workflows de CI/CD, configuraciones de Nginx en `nginx.conf`, empaquetados en `Dockerfile` o docker-compose.yml sin aprobación humana.
- **Empaquetado:** La aplicación es compilada por Node.js y servida a través de un contenedor Nginx expuesto por el puerto `80`.
- **Variables de compilación:** El script del `Dockerfile` reemplaza en caliente las direcciones de la app privada y de WhatsApp comercial en el archivo `environment.ts` durante la compilación.
- **Local Compose:** El compose expone la landing page en el puerto `8080` y define un perfil (`visual`) para lanzar las pruebas visuales con Playwright.
