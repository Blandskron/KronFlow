---
applyTo: "**/{tests,test,__tests__}/**/*"
---

# Convenciones de Testing

- **Flujos críticos:** Para auth, onboarding, tenant u operational agregue pruebas reproducibles con mocks/ambiente controlado; el smoke actual no los cubre.
- **Mocks:** Al configurar pruebas Angular, use `HttpTestingController`; nunca use tokens o credenciales reales.
- **No silenciar errores:** No omita assertions para ocultar regresiones.
