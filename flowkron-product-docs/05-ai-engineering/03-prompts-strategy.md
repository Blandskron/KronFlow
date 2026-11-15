# Estrategia objetivo de prompts

Versión: 1.0
Tipo: Target Architecture
Estado de implementación: `NOT_IMPLEMENTED`
Propietario previsto: por definir
Última verificación técnica: 2026-06-22

## Estado actual

No existe prompt registry, almacenamiento, versionado, render engine ni evaluación de prompts.

## Diseño propuesto

Cada prompt debe registrar nombre, versión inmutable, agente/tarea, owner, modelo compatible, variables tipadas, restricciones, ejemplos, schema de salida y estado (`draft|candidate|active|retired`).

## Reglas

- Separar instrucciones del sistema, contexto tenant, datos recuperados y contenido del usuario.
- Tratar contenido externo como no confiable.
- Validar outputs con schema; no ejecutar texto libre como comando.
- No incluir secretos ni PII innecesaria.
- Versionar cambios y ligar cada ejecución a prompt/model version.
- Prompts recomiendan; backend autoriza y ejecuta.

La activación exige evaluación offline, revisión de seguridad y rollback a versión anterior.
