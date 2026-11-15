# AGENTS.md

Fuente única de contexto e instrucciones agenticas para `flowkron-deploy`. Los adaptadores de otros agentes solo remiten aquí.

## Propósito y límites

El stack base integra IAM, Operational, Agent Core, frontends, correo, PostgreSQL y Redis. El conector Baileys de laboratorio arranca desconectado.

## Mapa

| Archivo | Responsabilidad |
| --- | --- |
| `docker-compose.yml` | Nombre del proyecto e includes del stack base |
| `compose/bootstrap.yml` | Inicialización de credenciales en volúmenes por servicio |
| `compose/infrastructure.yml` | PostgreSQL 18, Redis 7, named volumes y red |
| `compose/backend.yml` | Auth/operational, healthchecks, dependencias y bind mounts |
| `compose/frontend.yml` | Landing/app y build args públicos |
| `compose/whatsapp.yml` | Conector interno y volumen privado de sesión |
| `.env.example` | Contrato de configuración local sin secretos reales |
| `data/jwt-keys/` | Claves generadas locales, ignoradas; no leer |
| `data/auth-media/` | Media persistente del auth, ignorada; no leer |


## Topología real

- Los contenedores usan `flowkron-network`. Los gateways de correo y WhatsApp permanecen en la red interna.
- PostgreSQL/Redis persisten en named volumes.
- Auth monta volúmenes privados para claves JWT y media, y publica la clave JWT en otro volumen.
- Operational espera PostgreSQL saludable y monta la clave JWT pública RO.
- Auth espera Redis, PostgreSQL y Operational. En local prepara el primer workspace después de aplicar migraciones.
- La app espera auth, operational y agent-core. La landing espera auth.
- Agent Core declara dependencia Compose de auth y operational saludables.

## Invariantes

- Mantener servicios modulares en `compose/`; el root solo incluye modelos.
- Preservar nombres DNS/servicio `flowkron-*`, red compartida y healthchecks cuando afecten `depends_on`.
- Distinguir puerto interno del contenedor y puerto publicado configurable.
- URLs de frontend son build args públicos y deben ser alcanzables por el navegador; no usar DNS interno de Compose para ellas.
- Mantener funcional el arranque sin `.env`. Los secretos del init persisten por proyecto. La configuración explícita se proporciona por un entorno privado.
- No fijar credenciales/defaults personales ni usar `latest`.
- Cambios de DB/volumen/JWT/startup deben contemplar migración, rollback y pérdida de datos.

## Seguridad operacional

`docker compose config` expande variables y puede filtrar secretos. Para sintaxis usa:

```powershell
docker compose config --quiet
```

No captures la configuración expandida. No ejecutes `down -v`, `docker system prune`, rotación/borrado de claves, migraciones destructivas ni despliegues sin aprobación explícita y backup verificado.

Este stack se publica en loopback por defecto, con HTTP y debug para desarrollo local. La creación automática del primer workspace solo se ejecuta en loopback con debug. Revisa [docs/SECURITY.md](docs/SECURITY.md).

## Autorización

Permitido: lectura de YAML, `.env.example` y docs; validaciones no mutantes; cambios documentales; proponer cambios Compose.

Requiere aprobación: editar Compose/plantilla env, puertos/redes/volúmenes/dependencias, imágenes, bootstrap, secretos, datos, claves, despliegue o repositorios hermanos.

## Validación proporcional

- Docs: enlaces, referencias, fences y `git diff --check`.
- YAML/env: `docker compose config --quiet` sin `.env` y con overrides de ejemplo.
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
