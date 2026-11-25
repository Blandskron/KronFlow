# Contexto Empresarial

Auth no crea ni escribe tablas de contexto empresarial.

Responsabilidades de Auth:

- emitir JWT humano con `tenant_id` logico;
- coordinar provisioning/reprovisioning con Operational mediante endpoints internos;
- conservar la proyeccion de runtime operacional cuando aplique.

Responsabilidades fuera de Auth:

- `flowkron-operational-service` traduce `tenant_id` a `schema_name`;
- `flowkron-operational-service` crea tablas tenant para documentos/chunks/RAG;
- `flowkron-agent-core` consume contexto por API interna de Operational;
- `flowkron-front-app-angular` consume endpoints publicos de Agent Core.

Ningun flujo de Auth debe aceptar ni calcular `schema_name` para RAG.
