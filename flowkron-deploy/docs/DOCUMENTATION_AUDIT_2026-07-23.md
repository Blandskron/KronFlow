# Auditoría documental — 2026-07-23

> Historical record. The former bundled channel workflow was removed in the Flowkron transition. For the current topology, see the repository architecture.

Se contrastaron `docker-compose.yml`, los modelos Compose y la plantilla de configuración pública.

## Hechos confirmados

- El stack base incluye infraestructura, backends y frontends; `compose/automation.yml` no se incluye por defecto.
- PostgreSQL y Redis usan volúmenes nombrados; Auth monta claves JWT y media locales; Operational lee las claves.
- Agent Core depende de Auth y Operational saludables, pero la app privada no espera su salud antes de arrancar.
- Los build args de frontend son valores públicos y deben ser accesibles desde el navegador, no DNS interno de Compose.
- El stack no incorpora TLS, proxy global, backups, observabilidad ni preparación productiva.

La validación segura de Compose es `docker compose config --quiet`; no se capturó configuración expandida para evitar exponer secretos.
