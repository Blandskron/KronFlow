# Evaluación del runtime conversacional

El dataset sintético [v1](../../app/tests/fixtures/agent_evaluation.v1.json) prueba saludos, agradecimientos, solicitud de atención humana, falta de fuentes, recuperación débil, respuestas locales de dos empresas, generación simulada, límite de entrada y fallos de proveedor o contexto. Cada caso tiene un ID estable y una expectativa de respuesta o motivo de derivación.

## Ejecución en una instalación de desarrollo

Desde la raíz de `flowkron-agent-core`, con `requirements-dev.txt` instalado, el conjunto de evaluación se puede ejecutar sin credenciales ni red a servicios:

```powershell
python -m pytest app/tests/test_agent_evaluation.py app/tests/test_chat_provider.py -q
```

La evaluación parametrizada valida el esquema Pydantic de la respuesta, empresa y conversación, texto y referencias esperadas, y consistencia entre `requires_human`, `next_step` y la acción propuesta. Los fallos de proveedor se simulan en la frontera HTTP. Un caso adicional utiliza persistencia SQLite en memoria para comprobar que el mismo ID externo en dos empresas se mantiene aislado y que se registra la derivación por confianza insuficiente. Cada caso debe pasar antes de aceptar una modificación del runtime. Para actualizar expectativas existentes, registrar el motivo y ejecutar la suite completa.

## Presupuesto y observación

El agente conserva la pregunta y selecciona extractos completos en orden de recuperación. Cuenta caracteres Unicode, incluidos los delimitadores del prompt. Si el presupuesto no admite el primer extracto, devuelve una propuesta de derivación con motivo `chat_input_budget_exceeded`. La configuración del proveedor limita por separado la salida solicitada. [Configuración](CONFIG.md)

Con logging `INFO` para `app.infrastructure.llm.groq`, cada intento de llamada registra resultado, latencia e indicadores de uso. Se registran tokens si el proveedor devuelve enteros no negativos con un total consistente. `None` indica uso desconocido y `0` un cero informado. Se omiten prompts, respuestas, credenciales e identificadores de empresa. El bloqueo durante la preparación se registra en `app.application.orchestration.agent_runtime`. Estas señales miden intentos y uso observado. El cálculo de costo, el gasto acumulado por empresa y la persistencia de trazas integradas siguen pendientes.
