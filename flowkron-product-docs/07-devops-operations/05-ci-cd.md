# Integración y despliegue continuos

Versión: 1.1
Tipo: arquitectura objetivo
Estado: `NOT_IMPLEMENTED`
Última verificación: 2026-07-23

No existen workflows CI/CD versionados en los repositorios revisados.

## Gates propuestos

| Repositorio | Validaciones mínimas |
| --- | --- |
| Auth | compile/check, migraciones pendientes, tests, OpenAPI y seguridad |
| Operational | compile/import, OpenAPI, tests tenant cuando existan y migraciones |
| Agent Core | pytest, contrato, seguridad IA y provider mocks |
| App/Landing | build, lint cuando exista, smoke y accesibilidad |
| API Contracts | JSON Schema, YAML, OpenAPI lint y breaking changes |
| Deploy | Compose quiet, build, smoke y scan de imágenes |
| Product Docs | enlaces, estados, referencias, encoding y whitespace |

## Pipeline objetivo

```text
PR -> validaciones -> revisión -> artefactos inmutables
   -> staging -> migraciones -> smoke/E2E/security
   -> aprobación -> producción -> observabilidad
   -> rollback si falla
```

GitFlow documenta la gobernanza de ramas, pero no reemplaza un pipeline implementado.
