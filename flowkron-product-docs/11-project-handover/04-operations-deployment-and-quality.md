# Operación, despliegue, testing y calidad

## 1. Entorno disponible

| Entorno | Estado | Evidencia |
| --- | --- | --- |
| Local integrado | `IMPLEMENTED` | Docker Compose modular |
| Desarrollo compartido | `NOT_IMPLEMENTED` | Sin infraestructura versionada |
| QA/Staging | `NOT_IMPLEMENTED` | Sin configuración desplegable |
| Producción | `NOT_IMPLEMENTED` | Sin plataforma productiva verificable |

El proceso Railway existente es una guía de preparación y despliegue, pero la presencia de archivos `railway.toml` no demuestra que un ambiente remoto esté operativo ni que haya sido validado en esta entrega.

## 2. Stack local

El Compose base integra:

- PostgreSQL 18;
- Redis 7;
- Auth;
- Operational;
- Agent Core;
- Landing;
- App privada.


## 3. Persistencia local

| Recurso | Persistencia |
| --- | --- |
| PostgreSQL | Named volume |
| Redis | Named volume |
| Claves JWT | Bind mount, Auth RW y consumidores RO |
| Media Auth | Bind mount |

`docker compose down` conserva named volumes. Operaciones con `-v`, limpieza de volúmenes, claves o schemas son destructivas y requieren respaldo y autorización explícita.

## 4. Orden operativo

1. Preparar variables desde `.env.example` sin versionar secretos.
2. Validar Compose silenciosamente con `docker compose config --quiet`.
3. Levantar infraestructura y servicios según la guía de Deploy.
4. Confirmar healthchecks.
5. Ejecutar migraciones/seeds autorizados.
6. Verificar login, tenant, runtime y pantallas principales.

Los healthchecks son indicadores básicos, no pruebas de aceptación.

## 5. Matriz de calidad

| Repositorio | Evidencia de calidad | Brecha |
| --- | --- | --- |
| Auth | Checks Django y suite documentada | Cobertura de aislamiento, refresh reuse y flujos externos incompleta |
| Operational | Compile/import y scripts manuales | Sin suite automatizada; scripts de schema pueden ser destructivos |
| Agent Core | Pytest de health, plantillas, documentos, contexto y cross-tenant | Sin proveedor real ni E2E integrado |
| App | Build Angular y smoke visual externo | Sin runner/specs unitarios ni E2E autenticado |
| Landing | Build y smoke con screenshots | Sin tests unitarios ni baseline visual |
| Contracts | Validación JSON/YAML/docs | Sin lint semántico OpenAPI completo en pipeline |
| Deploy | Validación Compose estática | Sin smoke productivo, backup/restore o failover |

## 6. Smoke de aceptación recomendado

En un entorno descartable y autorizado:

1. Auth, Operational y Agent Core responden salud.
2. Landing carga y envía contacto con CSRF.
3. Usuario invitado verifica correo e inicia sesión.
4. Onboarding crea tenant y tokens nuevos.
5. Activación aprovisiona runtime y schema.
6. App carga `/auth/me`, conversaciones, leads y analytics.
7. Contexto Empresarial lista plantillas, sube documento y actualiza status.
8. Simulación recupera fuentes del tenant correcto.
9. Un segundo tenant no puede leer documentos o datos del primero.

Este smoke es una recomendación de entrega; no hay evidencia de que todo el recorrido haya sido automatizado o aprobado.

## 7. Logs y diagnóstico

- Auth y servicios backend generan logs estructurados/correlacionados de forma parcial.
- No registrar passwords, tokens, claves, payloads WhatsApp completos o PII innecesaria.
- Revisar logs de un servicio de manera acotada y conservar correlation ID.
- No existe agregación central, retención de logs definida ni alertas.

## 8. Backups y recuperación

No hay jobs de backup ni restore probado en los repositorios. Antes de producción se necesita:

- inventario de datos y volúmenes;
- política aprobada de RPO/RTO;
- backups cifrados y fuera del host;
- prueba periódica de restauración;
- responsables y evidencia de cada ejercicio.

## 9. CI/CD y releases

GitFlow está documentado como proceso organizacional, pero no hay pipelines versionados. Un pipeline mínimo debe validar contratos, tests/builds, seguridad, imágenes, migraciones, staging, aprobación productiva y rollback.

