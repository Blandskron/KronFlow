---
applyTo: "**/*.{ts,tsx,js,jsx,html,css,scss}"
---

# Convenciones Frontend

- **Arquitectura Angular:** Los componentes nuevos deben ser Standalone. La landing page utiliza una estructura sencilla donde la vista principal comercial se ubica bajo `features/landing/landing.component.ts`.
- **Tipado estricto:** Define siempre interfaces para los enlaces y propiedades visuales de la landing, evitando el tipo `any`.
- **Secretos:** No se permiten contraseñas ni llaves en duro. El número de WhatsApp y las URLs de la aplicación de negocio se configuran mediante variables en `environment.ts` y Docker.
- **Redirecciones:** Los enlaces para iniciar sesión o registrarse deben usar la variable `environment.appUrl` para apuntar de forma dinámica y correcta.
