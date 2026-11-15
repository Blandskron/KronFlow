# Inventario documental técnico

## 1. Secciones

| Sección | Contenido | Fuente |
| --- | --- | --- |
| `04-architecture` | Estado, servicios, datos, APIs, integraciones y ADR | Código + contratos |
| `06-security-compliance` | Controles técnicos, auth, RBAC, privacidad y backups | Código/configuración |
| `07-devops-operations` | Local, Docker, deploy, logs, monitoring y DR | Compose + configs |
| `11-project-handover` | Continuidad para desarrolladores | Síntesis de todos los repos |

## 2. Documentación canónica por cambio

| Cambio | Actualizar primero |
| --- | --- |
| Endpoint/payload | OpenAPI propietario + `flowkron-api-contracts` |
| Modelo Auth | `flowkron-auth-service/docs/DATA_MODEL.md` |
| Modelo/schema tenant | `flowkron-operational-service/docs/DATA_MODEL.md` |
| Runtime/contexto IA | `flowkron-agent-core/docs` |
| Ruta/pantalla App | `flowkron-front-app-angular/docs` |
| Landing/contacto | `flowkron-front-landing-angular/docs` |
| Compose/puerto/volumen | `flowkron-deploy/docs` |
| Estado transversal | `04-architecture/00-current-implementation-status.md` |
| Riesgo/deuda | `11-project-handover/05-known-gaps-and-continuity.md` |

## 3. Archivos de entrada

- `README.md`: índice técnico.
- `AGENTS.md`: reglas para mantener documentación.
- `11-project-handover/README.md`: lectura de recepción.
- `04-architecture/00-current-implementation-status.md`: matriz de capacidades.
- `04-architecture/12-service-catalog.md`: ownership.
- `04-architecture/13-contract-catalog.md`: contratos.
- `07-devops-operations/11-railway-deployment-runbook.md`: procedimiento Railway.

## 4. Regla de actualización

Un cambio se considera documentado cuando:

1. el repositorio propietario refleja el comportamiento;
2. el contrato compartido está sincronizado;
3. los consumidores conocidos fueron revisados;
4. tests/validaciones proporcionales se ejecutaron;
5. la vista transversal no contradice el runtime.
