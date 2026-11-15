---
applyTo: "**/*.py"
---

# Convenciones Python

- Sigue las convenciones existentes del proyecto (estilo Django, PEP8).
- Usa Python 3.13 como estándar recomendado.
- El gestor de dependencias es `pip` (`requirements.txt`). No agregues nuevas dependencias sin aprobación humana explícita.
- Para testing, utiliza el framework nativo de Django (`TestCase` de `django.test`).
- Utiliza la biblioteca `compileall` para linter estático rápido antes de guardar:
  ```bash
  python -m compileall -q apps config scripts manage.py
  ```
- Prefiere tipos explícitos (`typing`) cuando el proyecto los utilice.
- No ocultes errores con excepciones genéricas (`except Exception: pass`) sin la debida justificación técnica.
- Si cambias comportamiento en la lógica de negocio de un módulo, debes agregar o actualizar las pruebas correspondientes en el archivo `tests.py` o subdirectorio `tests/` del módulo afectado.
