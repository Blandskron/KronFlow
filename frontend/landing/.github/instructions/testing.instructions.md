---
applyTo: "**/{tests,test,__tests__}/**/*"
---

# Convenciones de Testing

- **Estado actual:**
  - No existe target ni suite unitaria configurada.
  - Playwright ejecuta smoke funcional y guarda screenshots, sin comparación contra baselines.
- **Flujos Críticos:** Si modifica el contenido visual o comportamiento de la landing page, ejecute los tests visuales de Playwright en `tests/visual/flowkron-landing.visual.spec.ts`.
- **No silenciar fallos:** No desactive assertions Playwright para ocultar regresiones. Si se agrega runner unitario, documentarlo primero.
