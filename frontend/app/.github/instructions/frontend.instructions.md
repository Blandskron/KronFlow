---
applyTo: "**/*.{ts,tsx,js,jsx,html,css,scss}"
---

# Convenciones Frontend

- **Arquitectura Angular:** Los componentes nuevos deben ser Standalone. Sigue la arquitectura de carpetas dividida en `features/` (lógica de negocio por dominios), `core/` (guards, interceptores, singleton services) y `shared/` (componentes reusables de interfaz de usuario).
- **Tipado estricto:** Define siempre interfaces para payloads e interfaces de API. Evita el uso del tipo `any`.
- **Estilos:** Usa Vanilla CSS (según las convenciones estéticas del proyecto) y el paquete Lucide Angular para iconos uniformes.
- **Ruteo:** Cualquier nueva página debe declararse en `app.routes.ts` con carga diferida (`loadComponent: () => import(...)`).
