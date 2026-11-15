# Glosario

| Término | Definición en Flowkron |
| --- | --- |
| Agent Core | Servicio de inteligencia conversacional y contexto empresarial independiente del canal |
| ApiError | Contrato estandarizado de error basado en problem details |
| ApiResponse | Envelope estándar de éxito para APIs Flowkron |
| Auth Service | Servicio IAM que emite JWT y administra identidad, tenants y RBAC |
| Correlation ID | Identificador compartido para seguir una operación entre requests/servicios |
| Entitlement | Capacidad habilitada o limitada por plan/suscripción |
| Gateway | Adaptador que recibe eventos de un canal y los transforma a un contrato interno |
| Ingest key | Secreto rotable que autentica un tenant/canal ante endpoints de ingestión |
| IAM | Identity and Access Management |
| Membership | Relación entre usuario y tenant |
| Multi-tenant | Arquitectura que sirve a varias empresas manteniendo aislamiento lógico/físico |
| Operational Service | Propietario del runtime y datos operacionales multi-schema |
| PII | Información personal identificable |
| RAG | Retrieval-Augmented Generation; recuperación de fuentes para contextualizar una respuesta IA |
| RBAC | Autorización basada en roles y permisos |
| Runtime tenant | Registro operacional que vincula tenant lógico, schema, plan, estado y credenciales de ingestión |
| Schema tenant | Namespace PostgreSQL físico aislado para datos de una empresa |
| Service account | Identidad de máquina que puede obtener JWT con scopes |
| Stub | Ruta o componente presente sin implementar su capacidad funcional |
| Tenant | Empresa cliente dentro de Flowkron |
| Tenant code | Identificador público de integración asociado al runtime |
| `schema_translate_map` | Mecanismo SQLAlchemy usado para dirigir modelos `tenant` al schema físico correcto |

