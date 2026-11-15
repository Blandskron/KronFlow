# Autorización y RBAC

**Versión:** 1.0
**Tipo:** Implementación parcial
**Última verificación:** 2026-06-22

## Roles canónicos

Los roles definidos por IAM son:

- `TENANT_OWNER`
- `TENANT_ADMIN`
- `MANAGER`
- `VENDEDOR`
- `AGENT_SUPERVISOR`
- `AGENT_OPERATOR`
- `VIEWER`

No deben inventarse nombres alternativos en documentación o clientes. Los permisos efectivos se calculan en IAM a partir de membresía, rol y asignaciones.

## Estado por capa

| Capa | Estado | Evidencia |
|---|---|---|
| Administración IAM | `IMPLEMENTED` | Permisos DRF, gestión de usuarios, membresías, roles y permisos |
| Identidad de tenant | `IMPLEMENTED` | Claims y membresía emitidos por IAM |
| API operacional | `PARTIAL` | Valida JWT y tenant, pero sus routers no hacen control granular de permisos |
| Frontend | `PARTIAL` | Usa datos de sesión y protege rutas; no reemplaza autorización del servidor |
| Agentes, IA y billing | `NOT_IMPLEMENTED` | No existe runtime autorizable |

## Regla de seguridad

Ocultar controles en Angular no autoriza una operación. Toda acción sensible debe validarse en el backend propietario del recurso. La brecha operacional debe resolverse mediante [ADR-007](../04-architecture/technical-decisions-adr/ADR-007-operational-authorization.md) antes de exponer operaciones sensibles en producción.
