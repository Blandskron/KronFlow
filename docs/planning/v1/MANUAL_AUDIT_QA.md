# Prueba manual de eventos de auditoría

Usa una empresa de prueba con `crm.manage` para producir un evento y `audit.read` para consultar el historial. El recorrido funciona con un contacto sintético y puede ejecutarse con WhatsApp desconectado. [Alta manual de un contacto](MANUAL_CRM_QA.md#crear-el-contacto-desde-la-interfaz)

1. Crea un contacto sintético, inicia su seguimiento y cambia su etapa. En la pestaña **Red** de las herramientas del navegador, copia el encabezado de respuesta `X-Correlation-ID` del `PATCH` que guardó la etapa. Es un UUID.
2. Abre **Configuración → Eventos de auditoría**. Filtra por **Cambio de etapa** y por el UUID copiado. Debe aparecer el evento correspondiente, con la etapa anterior y la nueva. **Abrir lead** debe llevar al lead que editaste.
3. Limpia el filtro de correlación y consulta los eventos anteriores si hay más de una página. **Más recientes** conserva el filtro por tipo. Un evento antiguo sin UUID puede mostrar **Sin correlación HTTP registrada**.
4. Abre la ruta en una cuenta de prueba sin `audit.read`. La consulta no está disponible. El API aplica el permiso igualmente si se llama de forma directa.

Registra el SHA, el UUID del caso sintético y el resultado. La página consulta una proyección histórica de auditoría. La entrega a consumidores, el checkpoint de replay y las suscripciones tienen verificaciones pendientes en FK-10. [Criterios de cierre](RELEASE_GATES.md#trabajo-en-curso-por-verificar)
