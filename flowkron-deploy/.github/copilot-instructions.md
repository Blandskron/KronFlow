# Instrucciones para GitHub Copilot

Usa [AGENTS.md](../AGENTS.md) como única fuente agentica y [docs/README.md](../docs/README.md) para documentación técnica.

- No leas, escribas ni muestres `.env`, PEM, media o secretos.
- No modifiques Compose, puertos, redes, volúmenes, datos o repositorios hermanos sin aprobación.
- Valida sintaxis con `docker compose config --quiet`; no imprimas configuración expandida.
- No recomiendes `down -v`, prune o regeneración de claves como diagnóstico rutinario.
- Actualiza documentación cuando cambie el modelo operativo.
