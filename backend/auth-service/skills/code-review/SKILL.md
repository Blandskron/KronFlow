---
name: code-review
description: Usa esta skill cuando se te solicite revisar la calidad del código, buscar bugs o verificar el cumplimiento de las convenciones arquitectónicas del proyecto.
---

# Skill de Revisión de Código

## Cuándo usar
- Antes de proponer cambios de lógica en cualquiera de las apps de Django.
- Cuando el desarrollador solicite una auditoría estática del código.
- Al analizar posibles cuellos de botella o ineficiencias en consultas SQL/ORM.

## Pasos operativos
1. **Analizar la arquitectura:** Verificar que el código respete la estructura de capas (Models -> Serializers -> Services -> Views).
2. **Inspeccionar Consultas ORM:** Comprobar que no existan problemas de N+1 consultas (usar `select_related` o `prefetch_related` donde corresponda).
3. **Chequear Seguridad:**
   - Validar que no haya secretos duros en código.
   - Confirmar que se valide la membresía y tenant antes de retornar información sensible.
   - Validar que las llamadas críticas requieran el decorador/middleware de MFA.
4. **Verificar Cumplimiento PEP8:** Ejecutar el comando de validación rápida compileall:
   ```bash
   python -m compileall -q apps config scripts manage.py
   ```

## Límites
- El agente no puede aprobar sus propias revisiones de código en entornos de control humanos sin el visto bueno de un desarrollador senior.
- No modificar el código de la aplicación de forma directa durante la fase de revisión.
