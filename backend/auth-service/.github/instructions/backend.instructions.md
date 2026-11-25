---
applyTo: "**/{apps,config}/**/*"
---

# Convenciones Backend

- **Arquitectura:** Sigue estrictamente la arquitectura por dominio y capas (Views -> Serializers -> Services -> Models). No mezcles lógica compleja de negocio directamente en las Views.
- **Entidades e Invariantes:** Las tablas IAM deben usar el prefijo `iam_`. Declara índices adecuados para consultas frecuentes y restricciones únicas donde corresponda.
- **Validación de Datos:** Los Serializers de DRF deben validar minuciosamente todo input y output de datos.
- **Aislamiento Multi-Tenant:**
  - Valida el tenant en el backend.
  - Comprueba la membresía del usuario antes de derivar peticiones a un tenant.
  - Asegura que el search_path de PostgreSQL cambie de forma aislada y sanitizada.
- **Auditoría:** Registra eventos críticos en la tabla de auditoría (`iam_audit_log`) para operaciones de seguridad (login, MFA, rotación de claves, etc.).
- **Compatibilidad de API:** No rompas contratos de API sin aprobación previa. Mantén la especificación de OpenAPI (`drf-spectacular`) actualizada.
