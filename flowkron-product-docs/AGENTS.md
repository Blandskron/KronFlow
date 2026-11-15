# AGENTS.md

Instrucciones para mantener la documentación técnica de Flowkron.

## Alcance

Este repositorio solo documenta código, arquitectura, APIs, datos, IA, seguridad técnica, infraestructura, operaciones, testing, deuda técnica y handover de desarrollo.

No agregues estrategia, PRD, research, roadmap, backlog, Scrum, pricing, ventas, marketing, customer success, SLA, material comercial o assets de marca.

## Repositorios fuente

- `flowkron-auth-service`
- `flowkron-operational-service`
- `flowkron-agent-core`
- `flowkron-front-app-angular`
- `flowkron-front-landing-angular`
- `smtp-http-blandskron`
- `flowkron-api-contracts`
- `flowkron-deploy`

## Reglas

- Código, configuración y contratos adoptados prevalecen.
- Usa los estados de `README.md`.
- Separa estado actual, brechas y objetivo.
- No conviertas UI, stub, mock, historia o configuración opcional en capacidad implementada.
- Conserva ADR y agrega notas de evidencia cuando cambie la realidad.
- Usa enlaces relativos.
- No copies secretos, `.env`, claves, tokens, credenciales, PII ni rutas personales.
- Actualiza primero la documentación del repositorio propietario.

## Validación

- UTF-8 válido.
- Enlaces Markdown relativos existentes.
- Fences de código cerrados.
- Sin whitespace problemático ni marcadores de conflicto.
- Contratos JSON/YAML válidos.
- Compose validado con `docker compose config --quiet`.
- `git diff --check` cuando exista metadata Git válida.
