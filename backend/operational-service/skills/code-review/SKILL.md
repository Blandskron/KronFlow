---
name: code-review
description: Usa esta skill para revisar calidad, aislamiento multi-schema, seguridad y contratos FastAPI.
---

# Revisión de código

1. Determina qué modelos están realmente importados en metadata; no mezcles `operations.py` con módulos legacy duplicados.
2. Comprueba que queries tenant usen `schema_translate_map` y que schemas persistidos provengan de sanitización controlada.
3. Revisa JWT/internal/ingest auth y verifica si el router aplica autorización RBAC, no solo autenticación.
4. Busca escrituras/DDL, transacciones parciales, queries N+1 y campos Pydantic ignorados por services.
5. Ejecuta:

```powershell
python -m compileall -q app scripts
```

No ejecutes scripts DB ni modifiques código cuando el encargo sea únicamente diagnóstico.
