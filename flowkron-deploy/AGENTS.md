# AGENTS.md

Fuente única de contexto e instrucciones agenticas para `flowkron-deploy`. Los adaptadores de otros agentes solo remiten aquí.

## Propósito y límites


## Mapa

| Archivo | Responsabilidad |
| --- | --- |
| `docker-compose.yml` | Nombre del proyecto e includes del stack base |
| `compose/infrastructure.yml` | PostgreSQL 18, Redis 7, named volumes y red |
| `compose/backend.yml` | Auth/operational, healthchecks, dependencias y bind mounts |
| `compose/frontend.yml` | Landing/app y build args públicos |
| `.env.example` | Contrato de configuración local sin secretos reales |
| `data/jwt-keys/` | Claves generadas locales, ignoradas; no leer |
| `data/auth-media/` | Media persistente del auth, ignorada; no leer |


## Topología real

- Todos los contenedores usan `flowkron-network` y publican puerto al host.
- PostgreSQL/Redis persisten en named volumes.
- Auth monta `data/jwt-keys` RW y `data/auth-media` RW.
- Operational monta las claves JWT RO y declara dependencia Compose de auth saludable; usa PostgreSQL por `OPERATIONAL_DATABASE_URL`.
- Auth declara dependencia Compose solo de Redis saludable; su entrypoint espera PostgreSQL usando `DATABASE_URL`.
- App depende solo de auth saludable; landing no declara dependencias.
- Agent Core declara dependencia Compose de auth y operational saludables.
- No hay dependencia de salud que garantice operational o agent-core antes de iniciar la app frontend.

## Invariantes

- Mantener servicios modulares en `compose/`; el root solo incluye modelos.
- Preservar nombres DNS/servicio `flowkron-*`, red compartida y healthchecks cuando afecten `depends_on`.
- Distinguir puerto interno del contenedor y puerto publicado configurable.
- URLs de frontend son build args públicos y deben ser alcanzables por el navegador; no usar DNS interno de Compose para ellas.
- Secretos obligatorios usan `${VAR:?mensaje}` y deben seguir siendo placeholders en `.env.example`.
- No fijar credenciales/defaults personales ni usar `latest`.
- Cambios de DB/volumen/JWT/startup deben contemplar migración, rollback y pérdida de datos.

## Seguridad operacional

`docker compose config` expande variables y puede filtrar secretos. Para sintaxis usa:

```powershell
docker compose config --quiet
```

No captures la configuración expandida. No ejecutes `down -v`, `docker system prune`, rotación/borrado de claves, migraciones destructivas ni despliegues sin aprobación explícita y backup verificado.

Este stack usa defaults locales peligrosos fuera de desarrollo: debug, seeds, migrations, collectstatic, generación JWT y creación de superusuario activados; DB/Redis/APIs publicados; HTTP sin TLS. Revisa [docs/SECURITY.md](docs/SECURITY.md).

## Autorización

Permitido: lectura de YAML, `.env.example` y docs; validaciones no mutantes; cambios documentales; proponer cambios Compose.

Requiere aprobación: editar Compose/plantilla env, puertos/redes/volúmenes/dependencias, imágenes, bootstrap, secretos, datos, claves, despliegue o repositorios hermanos.

## Validación proporcional

- Docs: enlaces, referencias, fences y `git diff --check`.
- YAML/env: `docker compose config --quiet` con un `.env` local ya gestionado por el usuario.
- Runtime autorizado: `docker compose ps`, health endpoints y logs acotados sin secretos.
- No afirmar que un healthcheck prueba la funcionalidad completa.

## Documentos canónicos

- [Índice](docs/README.md)
- [Arquitectura](docs/ARCHITECTURE.md)
- [Configuración](docs/CONFIGURATION.md)
- [Operación](docs/OPERATIONS.md)
- [Seguridad y producción](docs/SECURITY.md)
- [Validación](docs/VALIDATION.md)

## Terminado

El cambio valida silenciosamente, no expone secretos, conserva datos/topología, documenta impacto y declara cualquier prueba no ejecutada.
