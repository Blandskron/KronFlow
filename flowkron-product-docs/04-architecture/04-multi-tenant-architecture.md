# Arquitectura multi-tenant

Versión: 1.0
Tipo: Current State
Estado: `PARTIAL`

## Identidad y autorización en Auth

Un usuario accede mediante membership activa a un tenant activo. Los permisos efectivos son:

```text
permisos RBAC de la membership ∩ entitlements del plan
```

Los endpoints tenantizados aceptan `X-Tenant-ID`, query/body o claim según contrato; si el JWT contiene tenant, debe coincidir.

## Resolución operacional

```text
JWT humano
  -> validar RS256/issuer/audience/exp
  -> extraer tenant_id
  -> buscar tenant_runtime público
  -> exigir runtime active y plan distinto de Free
  -> obtener schema_name persistido
  -> schema_translate_map
  -> ejecutar query tenant
```

Ingest usa tenant code + ingest key y aplica la misma validación de runtime/plan.

## Provisioning

Auth llama Operational por contrato interno. Operational sanitiza el slug, crea un schema único, tablas/objetos activos y una ingest key mostrada una vez. Auth conserva una proyección del runtime.

## Agent Core y schemas por industria

`flowkron-agent-core` no crea bases de datos, no crea schemas y no decide en qué schema escribir. Su responsabilidad es procesar mensajes, aplicar RAG/reglas/memoria y devolver una respuesta estructurada. La resolución de persistencia queda unificada en Operational:

```text
Agent Core
  -> solicita memoria/contexto/trazas por puerto interno
  -> Operational valida runtime tenant
  -> Operational decide schema físico y variante por industria
  -> Operational ejecuta lectura/escritura en el schema correcto
```

Las tablas de agent core son transversales por capacidad, pero físicamente deben existir dentro del schema que Operational haya provisionado para el cliente. A futuro, si existen schemas diferentes por industria, Operational selecciona la plantilla/migración compatible; Agent Core nunca recibe ni calcula `schema_name`.

## Controles y brechas

- El schema no se toma directamente de headers/cliente.
- Operational valida identidad, runtime y plan.
- Los permisos granulares todavía no están conectados a routers de dashboard Operational.
- El rate limit de ingest es por proceso/memoria.
- No existe suite automatizada cross-tenant.
- Plantillas/módulos por industria son arquitectura objetivo, no implementación general actual.
- Implementado puerto interno Operational <-> Agent Core para documentos, chunks, status y retrieval RAG. Siguen pendientes memoria conversacional productiva, trazas persistidas en Operational y logs de accion.
