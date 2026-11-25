# Contexto Empresarial

La landing no participa en Contexto Empresarial, RAG ni persistencia tenant.

Responsabilidad de este frontend:

- marketing publico;
- contacto comercial;
- enlaces hacia registro/login del frontend privado;
- WhatsApp comercial.

El flujo de documentos del agente pertenece al frontend privado:

```text
flowkron-front-app-angular -> flowkron-agent-core -> flowkron-operational-service
```

No agregar llamadas desde landing a endpoints de Agent Core, Operational interno o schemas tenant.
