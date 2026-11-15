# Guía técnica de migración a Azure

Versión: 1.0
Tipo: arquitectura propuesta
Estado: `PROPOSED`
Última verificación: 2026-07-23

No existe infraestructura Azure versionada ni desplegada en estos repositorios. Esta guía define una opción técnica para migrar desde Docker Compose local.

## 1. Mapeo propuesto

| Componente actual | Azure propuesto |
| --- | --- |
| Auth / Operational / Agent Core | Azure Container Apps |
| Landing / App | Azure Static Web Apps o contenedores Nginx |
| PostgreSQL | Azure Database for PostgreSQL Flexible Server |
| Redis | Azure Managed Redis |
| Imágenes | Azure Container Registry |
| Media/documentos | Blob Storage |
| Secrets | Key Vault |
| Logs/métricas | Application Insights + Log Analytics |
| OpenAI opcional | Azure OpenAI |

## 2. Red y seguridad

- VNet e integración privada para PostgreSQL/Redis/Key Vault cuando sea posible.
- Solo frontends y APIs públicas expuestas.
- Interfaces `/internal/*` restringidas a red/identidad interna.
- TLS en todos los ingress.
- Managed identities para Key Vault/Storage/Registry.
- CORS limitado a dominios reales.
- Sin puertos de DB/Redis públicos.

## 3. Configuración

Separar:

- configuración pública de frontend en build;
- variables no sensibles por ambiente;
- secretos en Key Vault;
- claves JWT con rotación y montaje controlado;

## 4. Base de datos

La migración debe preservar:

- tablas IAM públicas;
- tablas runtime públicas de Operational;
- todos los schemas tenant;
- vistas, funciones y triggers;
- ownership/grants;
- codificación/timezone/extensiones requeridas.

Antes de migrar:

1. inventariar schemas/objetos;
2. probar dump/restore en staging;
3. verificar migrations Django y tenant;
4. ejecutar tests cross-tenant;
5. definir ventana y rollback.

## 5. Orden recomendado

1. Crear IaC y ambiente staging.
2. Configurar Registry, Key Vault, red y observabilidad.
3. Migrar PostgreSQL/Redis con datos descartables.
4. Desplegar Auth y validar JWT/SMTP.
5. Desplegar Operational y validar provisioning/schema.
6. Desplegar Agent Core y validar contexto.
7. Publicar frontends con URLs correctas.
9. Ejecutar smoke, E2E y pruebas cross-tenant.
10. Preparar cutover/rollback productivo.

## 6. Rollback

- Mantener artefactos anteriores inmutables.
- No aplicar migraciones irreversibles durante el primer cutover.
- Conservar backup verificado antes de mover tráfico.
- Documentar DNS, claves, sesiones y consistencia de datos.
- Revertir tráfico y restaurar DB solo mediante runbook aprobado.

## 7. Criterios de validación

- Health/readiness y dependencias.
- Login, refresh y tenant.
- Provisioning y migración de varios schemas.
- Contexto documental y retrieval.
- CORS y URLs públicas.
- Logs/correlation IDs.
- Secrets no expuestos.
- Backup/restore.
- Alarmas y rollback.

