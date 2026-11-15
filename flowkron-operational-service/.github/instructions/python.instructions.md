---
applyTo: "**/*.py"
---

# Convenciones Python

- Sigue las convenciones existentes del proyecto (estilo FastAPI, PEP8).
- Usa Python 3.12, que es la versión fijada por el `Dockerfile`.
- El gestor de dependencias es `pip` (`requirements.txt`). No agregues nuevas dependencias sin aprobación humana explícita.
- Usa SQLAlchemy 2.0. Alembic se reserva para el schema público; los schemas tenant requieren una estrategia multi-schema explícita y no se migran mediante revisiones Alembic actuales.
- Utiliza la biblioteca `compileall` para linter estático rápido antes de guardar:
  ```bash
  python -m compileall -q app scripts
  ```
- No ocultes errores con excepciones genéricas (`except Exception: pass`) sin la debida justificación técnica.
