# ADR-003 — Angular + Django + FastAPI

Estado: Aceptado e implementado
Fecha de verificación: 2026-06-22

## Decisión

- Dos SPA Angular 21: landing pública y aplicación privada.
- Django/DRF sobre Python 3.13 para IAM.
- FastAPI sobre Python 3.12 para operación multi-tenant.
- Nginx sirve cada build Angular.

## Consecuencias

Permite especialización y despliegue independiente, pero exige contratos OpenAPI claros, CORS coherente, observabilidad transversal y coordinación de releases.

## Alcance

La decisión no implica que exista una capa IA: no hay servicio/worker LLM, RAG o tool calling en el runtime actual.
