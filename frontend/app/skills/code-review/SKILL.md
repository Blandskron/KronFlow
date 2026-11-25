---
name: code-review
description: Usa esta skill para revisar Angular, auth, APIs, UI, accesibilidad y seguridad frontend.
---

# Revisión de código

1. Revisa standalone/strict typing, lazy routes y límites `core/features/shared`.
2. Audita guards, interceptor, token storage, tenant, permisos y refresh sin asumir autorización cliente.
3. Contrasta DTOs/endpoints con cada backend y diferencia envelopes auth/operational.
4. Comprueba responsive, temas, foco, teclado, labels y estados loading/error/empty.
5. Identifica placeholders, vistas read-only y métodos sin UI.
6. Ejecuta `npm run build`; usa smoke/validación de flujos según el cambio.

No modifiques código cuando el encargo sea únicamente diagnóstico.
