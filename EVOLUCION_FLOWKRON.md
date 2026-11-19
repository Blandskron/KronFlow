# Flowkron: análisis cruzado y tareas de evolución

Fecha: 18 de noviembre de 2026. Responsable del producto: Blandskron.

Actualización: tercera revisión cruzada de tres POC y ampliación selectiva a 27 tareas. FK-01 y FK-02 están implementadas y validadas en entorno descartable; FK-09 tiene una primera entrega de metadatos de empresa. Las demás tareas siguen pendientes. El análisis de nuevas ideas no las habilita automáticamente en el runtime.

## Objetivo y alcance

Extraer aprendizajes de una implementación previa de Blandskron para mejorar Flowkron. La decisión es evolucionar los servicios existentes, conservando sus límites y su experiencia Angular. No se propone incorporar otra aplicación, reemplazar IAM ni mantener un segundo sistema de contactos, conversaciones o sesiones.

El análisis inicial fue estático: código, contratos, configuración, documentación y pruebas existentes. En ese análisis no se levantaron servicios ni se ejecutaron suites funcionales. La ejecución posterior de tareas se registra en el apartado siguiente, separada del diagnóstico inicial.

## Avance de ejecución

**FK-01 implementada y validada en entorno descartable (18 de noviembre de 2026).** Se amplió `mensajes_dashboard` con identidad externa/proveedor, dirección, canal, conexión, tipo, estado reportado y fecha de registro. La migración `tenant_schema_v3` conserva historial y admite escritores anteriores. Se alineó el contrato Operational `v0.4.0` y el conector guarda el ID propio de cada respuesta.

Validación: 9 pruebas FK-01 aprobadas, incluidas migración repetida, rollback, concurrencia y aislamiento en PostgreSQL 18.3 temporal; 10 pruebas del conector aprobadas. La suite Operational completa no pudo validar `test_security.py`: su import falla por una incompatibilidad previa entre Starlette instalado y el cliente HTTP declarado. No se modificaron dependencias. La [decisión técnica y procedimiento](flowkron-operational-service/docs/MESSAGE_IDENTITY.md) documenta alcance y rollout.

No se migró ninguna base de la instalación ni se desplegó el cambio. Ese paso permanece pendiente para un despliegue autorizado. La entrega inicial de FK-01 no recuperaba turnos incompletos; se añade a continuación el avance posterior.

**FK-02 implementada y validada en entorno descartable (18 de noviembre de 2026).** Operational conserva etapas de turno, lease, respuesta preparada y derivación humana atómica. El conector retoma generación/preparación recuperables y reintenta registrar una confirmación sin volver a enviar. Un envío ambiguo queda en `unknown`, consultable mediante API; una operación privada registra evidencia externamente verificada sin transmitir otro mensaje. No se reproducen automáticamente entradas históricas sin turno.

Validación FK-02: 13 pruebas PostgreSQL/ASGI aprobadas y 19 pruebas del conector aprobadas; las 9 pruebas FK-01 también pasaron con el esquema ampliado. Se probaron concurrencia, caducidad, tokens obsoletos, rollback, fallos antes/después del envío, retiradas previas al envío, aislamiento y reconciliación tras reinicio. Se conservan las limitaciones de la suite anterior basada en `TestClient`. Ver [diseño, migración v4 y runbook](flowkron-operational-service/docs/TURN_RECOVERY.md).

FK-02 no implementa aún un worker que busque pendientes después de reiniciar ni una cola durable: tras agotar los reintentos se necesita una nueva entrega/reclamación. Esa automatización es FK-03. Tampoco cierra toda la política de retiradas concurrentes de FK-04. No se aplicó la migración a la instalación ni se usaron proveedores reales.

**FK-09, primera entrega pequeña:** los metadatos de éxito y error de Operational identifican la empresa por `TenantContext.auth_tenant_id`, conservando el principal autenticado como fallback. No usan cabeceras no verificadas como identidad. Cuatro pruebas específicas y el recorrido ASGI de turnos cubren prioridad del contexto, compatibilidad, 200/409 y ausencia de identidad ante 401. La correlación completa, métricas y vista de diagnóstico siguen pendientes: FK-09 queda parcial.

La segunda revisión incorpora propuestas de acciones, supervisión humana, memoria conversacional, actualización de leads, agenda, correo, integraciones por empresa, notificaciones y evaluación del agente. Se amplían tareas existentes cuando el aprendizaje ya tiene un propietario; solo se crean IDs nuevos para capacidades distintas. La publicación Git del trabajo pendiente fue solicitada expresamente por el usuario; no implica un despliegue.

Se revisaron en profundidad el conector, ingestión, conversaciones, runtime de IA y pantallas relacionadas; también se contrastaron IAM, contratos, correo, landing, despliegue y CI. No es una revisión exhaustiva de cada archivo ni una auditoría de seguridad.

El documento se mantiene en la raíz porque combina análisis y tareas de evolución, contenido excluido del repositorio de documentación técnica. Todas las tareas comienzan pendientes. Los enlaces apuntan únicamente a archivos de Flowkron que permanecen disponibles.

## Conclusión

La mayor oportunidad es completar el ciclo operativo de la conversación: recepción recuperable, respuesta trazable, atención humana y extensibilidad por eventos. Añadir más pantallas o tipos de mensajes antes de resolver ese ciclo aumentaría las capacidades sobre una entrega todavía frágil.

Flowkron ya supera varios límites de la implementación previa: identidad de usuarios y permisos, consentimiento explícito, separación de datos por empresa, límites de admisión, restauración de sesiones y reconexión acotada. Estos controles deben mantenerse al introducir cada mejora.

## Comparación de enfoques

La columna de referencia resume código inspeccionado antes de retirar la implementación previa. Sus rutas internas se describen sin enlazarlas para que el documento no dependa de una carpeta eliminada.

| Área | Evidencia observada en la referencia | Estado de Flowkron | Decisión |
| --- | --- | --- | --- |
| Sesiones | Entidades empresa/instancia; estado, fechas y motivo de desconexión | Sesión por empresa, restauración al iniciar y reconexión con espera exponencial | Añadir diagnóstico e historial; conservar la política actual de reconexión |
| Proveedor de canal | Interfaz para conectar, consultar, enviar texto y multimedia | Clase de conexión concreta y normalización de texto | Introducir un puerto pequeño cuando se amplíen capacidades; evitar abstracciones duplicadas |
| Mensajes | Dirección, tipo, identificador del proveedor y estado en un registro | Texto guardado en `mensajes_dashboard`; deduplicación separada en `mensajes_procesados` | Completar identidad y ciclo del mensaje en el modelo realmente utilizado |
| Entrega y lectura | Estados y eventos declarados; no se encontraron handlers que actualicen entregado/leído | Endpoint de estado actualiza el JSON de conversación, sin recibos de cada mensaje desde el conector | Implementar recibos reales; una enumeración no constituye una capacidad |
| Webhooks | Suscripciones por empresa/instancia, selección de eventos y firma HMAC | Existe un schema de sobre y una interfaz reservada; no se observó un despachador equivalente en el flujo WhatsApp | Adoptar y ajustar contratos existentes antes de implementar entrega |
| Trabajos | Worker con cola Redis opcional y reintentos; sin Redis usa reintentos dentro del proceso | Cola entrante acotada en memoria y serial por sesión | Persistir trabajo y recuperación sin perder límites ni prioridad de BAJA |
| Inbox | Conversación, ficha técnica de contacto y envío manual de prueba | Historial de solo lectura, búsqueda local y avisos de atención humana | Convertir el handoff en operación real con permisos y coordinación humano/IA |
| Multimedia | Envío de imagen/audio/video/documento por URL; recepción reconoce tipo y algunos metadatos | Normalización activa admite texto directo; no entrega adjuntos al CRM | Añadir recepción y envío por etapas con almacenamiento privado |
| Credenciales | Claves por empresa con hash, prefijo y revocación | JWT de usuarios, permisos y credenciales internas/ingestión | Conservar IAM; proponer credenciales de automatización solo para consumidores externos |
| Persistencia | Snapshot en memoria; cada mutación borra y reinserta todas las tablas en PostgreSQL | ORM, schemas por empresa y aprovisionamiento con triggers | No trasladar el almacén de snapshots ni sus escrituras globales |
| Observabilidad | Logs por empresa/instancia, eventos y panel de diagnóstico | Auditoría IAM, eventos Operational y logs del conector separados | Correlacionar el recorrido completo y mostrar acciones de recuperación |
| Documentación y calidad | API documentada y panel explicativo; sin script de pruebas en el package principal revisado | Contratos versionados y CI para servicios, frontends y Compose | Reutilizar la infraestructura actual; comprobar correspondencia contrato/runtime |

## Base actual que debe conservarse

- [Conector y sesiones](flowkron-baileys-services/src/connection.ts): invalida sockets anteriores, serializa guardado de credenciales, limpia QR y limita reconexiones; cinco reintentos para desconexiones transitorias y nueva vinculación para causas permanentes.
- [Cola de entrada](flowkron-baileys-services/src/inbound-queue.ts): limita admisión y reserva capacidad para retiros de consentimiento. La durabilidad sigue pendiente.
- [Pipeline del canal](flowkron-baileys-services/src/ingest.ts): normaliza texto, consulta consentimiento, procesa ACEPTO/BAJA, ingiere, consulta al agente y registra respuesta. Deduplica la entrada mediante Operational.
- [IAM](flowkron-auth-service/apps/tenants/views.py): la gestión de conexión pasa por membresía y permiso `whatsapp.connect`; el navegador no recibe la credencial interna del conector.
- [Operational](flowkron-operational-service/app/services/tenant_provisioning_service.py): crea estructuras por empresa y actualiza resúmenes mediante triggers. No corresponde reconstruir ese resumen en otro almacén.
- [Agente](flowkron-agent-core/app/application/orchestration/agent_runtime.py): consulta contexto, puede usar un proveedor de IA y deriva ante falta de información. Hay rutas con persistencia propia y un flujo stateless usado en modo Operational; no deben confundirse sus capacidades.
- [Correo Blandskron](smtp-http-blandskron/README.md): ya ofrece idempotencia y separación entre salud y disponibilidad. Es un precedente interno útil, sin convertir correo en propietario de eventos WhatsApp.
- [CI](.github/workflows/validate.yml) y [revisión de publicación](RELEASE_READINESS.md): ya definen pruebas y límites de la demo local. No se infiere preparación productiva de la existencia de Compose.

## Brechas verificadas y consecuencias

1. **Entrada deduplicada no equivale a turno terminado.** `tenantIngest` guarda la entrada y abandona si una repetición devuelve `duplicate`. Si falla después el agente, el handoff o el envío, repetir la entrada no retoma esas etapas. Si el envío funciona pero falla su registro, el CRM puede omitir la respuesta enviada. Es una conclusión del orden del código, pendiente de reproducción mediante fallos controlados.
2. **La cola no sobrevive al proceso.** Conserva funciones en memoria y ejecuta un trabajo a la vez por sesión. No hay recuperación de trabajo pendiente después de un cierre; una llamada lenta al agente retiene los trabajos ordinarios de esa empresa. BAJA tiene prioridad entre pendientes, pero no interrumpe por sí sola un trabajo ya iniciado.
3. **El modelo activo requiere evolución explícita.** [Ingestión](flowkron-operational-service/app/services/ingest_service.py) y [consultas](flowkron-operational-service/app/services/conversation_service.py) importan `Message` desde [operations.py](flowkron-operational-service/app/tenant_models/operations.py), con tabla `mensajes_dashboard`. El modelo separado en [message.py](flowkron-operational-service/app/tenant_models/message.py) tiene otra estructura y no prueba que el flujo activo guarde esos campos. Cambiar solo ese archivo no resolvería la brecha.
4. **El handoff registra una necesidad, pero falta el cierre operativo.** La ingestión marca el lead para atención humana y [notificaciones](flowkron-front-app-angular/src/app/domains/dashboard/features/notifications-page/notifications-page.component.ts) lo consulta. Las [rutas de conversación](flowkron-operational-service/app/api/v1/conversations.py) revisadas solo ofrecen lectura; el [cliente del inbox](flowkron-front-app-angular/src/app/domains/conversations/data-access/conversations-api.service.ts) tampoco envía mensajes.
5. **La paginación visible no limita todo el trabajo.** `list_conversations` carga las filas, filtra y ordena en Python y finalmente recorta; el [inbox](flowkron-front-app-angular/src/app/domains/conversations/features/chats-page/chats-page.component.ts) solicita las primeras 100 conversaciones y busca localmente. El historial de mensajes sí ofrece páginas: conservarlo.
6. **El diagnóstico de conexión pierde detalle en el recorrido.** El snapshot del conector y la respuesta IAM exponen estado y QR; no ofrecen una cronología, motivo normalizado, próxima reconexión ni agotamiento de intentos al operador.
7. **Contratos existentes no garantizan adopción.** El [sobre de webhooks](flowkron-api-contracts/schemas/webhooks/webhook-envelope.schema.json), los [jobs](flowkron-api-contracts/schemas/jobs/async-job.schema.json) y la [interfaz reservada](flowkron-api-contracts/README.md) requieren verificar su correspondencia con runtime. El README de arquitectura y el índice técnico también reflejan cortes distintos respecto del conector y deben reconciliarse.

## Patrones que no deben trasladarse

El valor de la referencia está en sus conceptos, no en asumir que su implementación es una base productiva:

- Autenticar una clave de empresa sin usar su contexto para autorizar cada recurso. El hook revisado valida la clave, pero no adjunta su empresa a las rutas revisadas; filtrar por un ID enviado por el cliente no sustituye autorización.
- Guardar una clave operativa de API en `localStorage` como mecanismo de login del panel.
- Reescribir tablas completas desde un snapshot por cada mensaje, log o uso de una clave; crea contención y riesgo de sobrescritura entre procesos.
- Reconectar inmediatamente sin la clasificación y límites que ya existen en Flowkron.
- Tratar la aceptación de un trabajo como entrega al destino. El despacho usa `allSettled`; el endpoint de prueba puede contestar `delivered: true` sin confirmar la entrega efectiva al webhook seleccionado.
- Usar destinos globales de automatización que reciben eventos de distintas empresas sin configuración individual, o realizar peticiones a URLs arbitrarias sin controlar redirecciones, timeout y redes privadas.
- Equiparar reconocimiento del tipo de adjunto con descarga, almacenamiento y reproducción. Tampoco asumir recibos de lectura porque sus nombres aparecen en un schema.

## Tareas de mejora y evolución

Estado actual: **FK-01 y FK-02 implementadas y validadas en entorno descartable; FK-09 parcial (metadatos de empresa); demás tareas pendientes / propuestas**. P0 significa integridad y recuperación; P1, operación cotidiana; P2, extensibilidad. S/M/L son tamaños relativos, no compromisos de fechas. Los responsables indicados son componentes propietarios, no personas asignadas.

| ID | Prioridad | Tarea | Propietario | Tamaño | Depende de |
| --- | --- | --- | --- | --- | --- |
| FK-01 | P0 | Alinear contratos y modelo activo de mensajes — implementada; migración de instalaciones pendiente | Operational + Contratos | M | — |
| FK-02 | P0 | Recuperar etapas incompletas del turno — implementada; migración v4 de instalaciones pendiente | Operational + Conector | L | FK-01 |
| FK-03 | P0 | Persistir trabajos con admisión acotada | Operational + Conector + Deploy | L | FK-02 |
| FK-04 | P0 | Mantener consentimiento durante trabajos y reintentos | Operational + Conector | M | FK-02; completar con FK-03 |
| FK-05 | P1 | Diagnóstico accionable de conexión | Conector + IAM + CRM | M | — |
| FK-06 | P1 | Atención humana y envío desde el CRM | Operational + IAM + CRM + Conector | L | FK-02, FK-04 |
| FK-07 | P1 | Recibos y estados reales de cada mensaje | Operational + Conector + CRM | M | FK-01, FK-02 |
| FK-08 | P1 | Búsqueda, páginas y lecturas del inbox | Operational + CRM | M | FK-01 |
| FK-09 | P1 | Trazas y métricas del recorrido completo — parcial: metadatos de empresa corregidos | Todos los servicios del recorrido | M | FK-01; ampliar con FK-02, FK-03 |
| FK-10 | P2 | Eventos de dominio y suscripciones por empresa | Operational + Contratos | M | FK-01, FK-02 |
| FK-11 | P2 | Entrega fiable y diagnóstico de webhooks | Operational + Deploy + CRM | L | FK-03, FK-09, FK-10 |
| FK-12 | P2 | Credenciales acotadas para automatizaciones | IAM + Operational | M | FK-10 |
| FK-13 | P2 | Adjuntos privados por etapas | Operational + Conector + CRM | L | FK-01, FK-02, FK-04 |
| FK-14 | P2 | Preparar varias conexiones y proveedores | Conector + IAM + Contratos | L | FK-01, FK-05, FK-07 |
| FK-15 | P1 | Pruebas de recuperación y operación reproducible | Deploy + componentes afectados | L | Incremental desde FK-01 |
| FK-16 | P1 | Reconciliar documentación con la implementación | Raíz + documentación propietaria | S | —; actualizar por cada entrega |
| FK-17 | P1 | Propuestas de acciones tipadas y ejecución autorizada | Agent Core + Operational + Contratos | L | FK-02, FK-03, FK-04 |
| FK-18 | P1 | Revisar, aprobar y rechazar acciones desde el CRM | Operational + IAM + CRM | M | FK-17; coordinación con FK-06 |
| FK-19 | P1 | Control efectivo de IA y configuración por empresa | Operational + Agent Core + IAM + CRM | M | FK-04; ampliar con FK-03 y FK-17 |
| FK-20 | P1 | Memoria conversacional acotada y consistente | Operational + Agent Core | L | FK-01, FK-02, FK-04 |
| FK-21 | P1 | Enriquecer leads con datos confirmados | Operational + Agent Core + CRM | M | FK-17, FK-20 |
| FK-22 | P2 | Agenda conversacional con disponibilidad y confirmación | Operational + Agent Core + CRM | L | FK-17, FK-18, FK-20, FK-24 |
| FK-23 | P2 | Correo comercial vinculado a conversación | Operational + Correo Blandskron + CRM | L | FK-17, FK-18; FK-24 si se delega un buzón |
| FK-24 | P2 | Integraciones delegadas y credenciales por empresa | IAM + Operational + Deploy + CRM | L | FK-04, FK-09 |
| FK-25 | P1 | Centro de notificaciones de negocio y entregas | Operational + CRM + Correo Blandskron | M | FK-02, FK-03, FK-09; FK-17 para acciones |
| FK-26 | P1 | Evaluación del agente, trazas y presupuestos | Agent Core + Operational + Contratos | M | FK-09, FK-20; ampliar con FK-17 |
| FK-27 | P1 | Resolver solicitudes de privacidad y verificar retención | Operational + IAM + CRM + Deploy | L | FK-03, FK-04, FK-09 |

### FK-01 — Alinear contratos y modelo activo de mensajes

**Problema:** identidad externa, estado y datos del proveedor no están unidos al registro de mensaje que consulta el CRM.

**Trabajo:** documentar la ruta real de escritura/lectura; decidir la evolución de `mensajes_dashboard`, `mensajes_procesados` y resúmenes; añadir identidad del canal, dirección, tipo, ID externo y del proveedor, estado y fechas necesarias. Mantener compatibilidad con registros existentes. Resolver el destino del modelo alternativo mediante decisión técnica y migración, sin abrir una tercera fuente de verdad.

**Aceptación:** migración sobre una empresa existente y otra nueva; historial preservado; unicidad definida por empresa/conexión/canal/ID externo; duplicados concurrentes con resultado determinista; mapeo entre ID interno y del proveedor consultable. Especificaciones y ejemplos reflejan la implementación.

### FK-02 — Recuperar etapas incompletas del turno

**Problema:** el marcador de entrada procesada impide reanudar respuestas incompletas.

**Trabajo:** guardar etapas del turno y una intención de respuesta transaccional en Operational. Separar entrada registrada, generación pendiente, respuesta preparada, envío pendiente, envío confirmado/fallido y resultado desconocido. Guardar una respuesta generada antes de enviarla para reutilizarla al reintentar. Hacer idempotentes también handoff y efectos internos.

**Aceptación:** fallos inducidos después de cada etapa se pueden recuperar; una entrada duplicada retoma trabajo incompleto; fallar al registrar una respuesta enviada permite reconciliarla. Un timeout de envío con resultado desconocido queda visible y no provoca reenvío ciego. No prometer entrega exactamente una vez cuando el proveedor no permite demostrarla.

**Ampliación de la segunda revisión:** las acciones externas y sus confirmaciones también son etapas recuperables. Si el proveedor completó una operación y falló su persistencia local, reconciliar su ID antes de repetirla. Una respuesta inmediata confirma recepción de la solicitud; solo un resultado comprobado permite anunciar que la operación terminó.

**Entrega FK-02:** el ciclo WhatsApp de generación, respuesta, handoff y confirmación está implementado; la extensión a futuras acciones de correo/agenda depende de FK-17/FK-22/FK-23. La incertidumbre de envío queda bloqueada para reenvío automático. El despliegue necesita `tenant_schema_v4`; no se habilitó ninguna integración de negocio nueva.

### FK-03 — Persistir trabajos con admisión acotada

**Problema:** los trabajos pendientes desaparecen al reiniciar y una operación lenta bloquea la sesión.

**Trabajo:** respaldar trabajos e intenciones en almacenamiento durable. Evaluar primero una tabla de trabajos/outbox en PostgreSQL con reclamación y vencimiento de lease; utilizar Redis si aporta una necesidad concreta y se configura su persistencia. Preservar orden por conversación y repartir capacidad entre conversaciones y empresas. Limitar cola, concurrencia, intentos y tiempo; separar fallos definitivos y permitir reejecución controlada.

**Aceptación:** matar y reiniciar el worker no pierde trabajos ya aceptados durablemente; dos workers no ejecutan simultáneamente el mismo trabajo reclamado; un lease vencido se recupera; saturación devuelve un rechazo identificable o sigue una política explícita. La garantía comienza en la aceptación durable: no se atribuye al proveedor recuperación de mensajes que Flowkron no llegó a guardar.

**Ampliación de la segunda revisión:** acción y evento de despacho se guardan juntos mediante outbox. Evitar `commit` seguido de publicación sin reconciliación, extracción destructiva sin reconocimiento y orden LIFO que postergue indefinidamente trabajos antiguos. El worker reclama una acción desde un estado permitido, consulta la política vigente y trata un tipo desconocido como rechazo explícito. No mantiene una transacción SQL abierta durante llamadas de red ni simula éxito cuando no ejecutó el proveedor.

### FK-04 — Mantener consentimiento durante trabajos y reintentos

**Problema:** priorizar BAJA entre pendientes no cubre una respuesta que ya está en generación o esperando reintento.

**Trabajo:** versionar o fechar decisiones de consentimiento, conservar su evidencia mínima y verificar la autorización vigente antes de generar y justo antes de enviar. Cancelar trabajos incompatibles tras BAJA. Mantener capacidad reservada para retiros y definir el tratamiento de una retirada mientras el proveedor ya procesa un envío.

**Aceptación:** BAJA durante generación, espera o recuperación impide nuevos envíos de contenido ordinario todavía no iniciados; un retiro repetido es idempotente; reiniciar no reactiva trabajos cancelados. Queda documentado el límite de un envío ya iniciado externamente, sin prometer cancelación retroactiva.

### FK-05 — Diagnóstico accionable de conexión

**Problema:** el usuario ve el estado, pero carece de información para distinguir espera transitoria y necesidad de intervención.

**Trabajo:** añadir fechas de transición, última conexión, causa normalizada, cantidad de intentos y próxima acción. Propagar los campos permitidos por IAM y mostrarlos en la pantalla existente. Conservar QR efímero y privado; registrar su cambio como metadato, nunca su contenido.

**Aceptación:** cierre de sesión, desconexión transitoria y agotamiento de reintentos muestran acciones distintas; acceso limitado por empresa y permiso; los errores no exponen credenciales. Reinicio y expiración del QR no muestran un código anterior como vigente.

### FK-06 — Atención humana y envío desde el CRM

**Problema:** pedir un humano genera un aviso, pero el operador no puede completar la atención desde el inbox actual.

**Trabajo:** crear permisos de responder, asignar y cerrar; endpoints de toma/liberación, asignación, pausa de IA, respuesta y resolución. El destinatario y la conexión se resuelven desde la conversación autorizada. Enviar mediante FK-02, con autor humano y auditoría; actualizar la pantalla de notificaciones existente.

**Aceptación:** un lector no puede responder; otra empresa no puede acceder al hilo; dos operadores reciben una resolución determinista de toma; el agente deja de responder durante control humano; doble clic no duplica envío; resolver y devolver a IA queda registrado.

**Ampliación de la segunda revisión:** distinguir estado del hilo, responsable asignado y política de automatización. Mostrar quién responde y cuándo tomó control. Un hilo pausado no debe producir una nueva respuesta automática genérica por cada entrada; recibir y guardar mensajes sigue funcionando. Un ajuste de interfaz no cuenta como pausa si el worker o el envío no lo verifica.

### FK-07 — Recibos y estados reales de cada mensaje

**Problema:** el estado agregado de conversación no representa entrega o lectura de una respuesta concreta.

**Trabajo:** capturar eventos disponibles del proveedor, vincularlos mediante su ID y actualizar estados por mensaje. Distinguir encolado, envío aceptado, entregado, leído, fallo y resultado desconocido. Mostrar únicamente estados respaldados por evidencia del canal.

**Aceptación:** recibos repetidos y fuera de orden no hacen retroceder el estado; el mensaje correcto cambia dentro de su empresa/conexión; mensajes antiguos sin recibos muestran estado desconocido; errores conservan un motivo utilizable sin contenido sensible.

### FK-08 — Búsqueda, páginas y lecturas del inbox

**Problema:** búsqueda sobre las primeras 100 conversaciones y filtros posteriores a cargar filas no escalan con el historial.

**Trabajo:** ejecutar filtros, orden y paginación de conversaciones en SQL; agregar búsqueda por contacto y contenido según un alcance definido; aprovechar resúmenes e índices existentes y medir planes de consulta. Exponer `no_leidos` y definir lectura por usuario o compartida por equipo antes de implementar el reset. Conservar la carga de mensajes anteriores.

**Aceptación:** un contacto fuera de la primera página aparece en búsqueda; orden estable ante nuevas entradas; abrir un hilo actualiza el indicador según la semántica elegida; otras empresas permanecen aisladas. Adjuntar medición reproducible con volumen representativo; fijar el presupuesto de latencia antes de dar la tarea por terminada.

### FK-09 — Trazas y métricas del recorrido completo

**Problema:** logs y eventos separados dificultan explicar por qué una consulta no recibió respuesta.

**Trabajo:** propagar identificadores de correlación de mensaje, turno, trabajo y entrega; registrar transiciones estructuradas. Medir profundidad/edad de cola, rechazos, latencia, fallos del agente, envíos desconocidos y desconexiones. Añadir una vista de diagnóstico autorizada, enlazada a la conversación.

**Aceptación:** un operador autorizado distingue entrada recibida, generación fallida y entrega fallida usando un mismo ID; redacción de secretos y datos personales comprobada; métricas sin teléfonos o IDs de conversación como etiquetas de alta cardinalidad; retención definida.

**Ampliación de la segunda revisión:** unir mensaje → ejecución del agente → propuesta → decisión de política/aprobación → trabajo → resultado del proveedor → notificación. Registrar actor autenticado y versiones, con vistas resumidas en el CRM; payloads técnicos completos quedan restringidos. La trazabilidad específica de IA se completa con FK-26 y debe existir también en modo Operational.

### FK-10 — Eventos de dominio y suscripciones por empresa

**Problema:** existe un contrato de sobre, pero falta un flujo adoptado de eventos operativos reutilizables.

**Trabajo:** definir eventos efectivamente emitidos para mensajes, conexiones y atención humana; incluir identidad estable de evento, versión, empresa y correlación. Revisar cómo ampliar el sobre actual y dónde transportar la firma; cualquier cambio incompatible sigue el versionado existente. Suscripciones limitadas a la empresa autenticada, con selección de eventos y payload mínimo.

**Aceptación:** eventos se crean junto con la transacción de dominio; rollback no publica un evento; payloads validan contra schemas versionados; una suscripción no puede observar otra empresa. QR, credenciales, documentos completos y texto de conversaciones no se incluyen por defecto.

### FK-11 — Entrega fiable y diagnóstico de webhooks

**Problema:** automatizar requiere distinguir configuración, aceptación, intentos y entrega efectiva.

**Trabajo:** consumir outbox con reintentos acotados, espera exponencial, jitter y cola de fallos; limitar timeout, tamaño y concurrencia. Firmar bytes exactos con marca temporal y protección contra repetición; rotar secretos. Validar destino, resolución DNS, redes privadas y redirecciones antes de conectar. Registrar intentos sin revelar el secreto. La prueba debe dirigirse solo a la suscripción elegida y usar datos sintéticos.

**Aceptación:** reiniciar conserva entregas; respuestas 429/5xx siguen política documentada; un 4xx definitivo termina según clasificación; reejecución conserva identidad de evento. El receptor puede deduplicar; una pantalla distingue pendiente, fallido y entregado. URLs internas y redirecciones no autorizadas se rechazan.

### FK-12 — Credenciales acotadas para automatizaciones

**Problema:** integraciones externas necesitan identidad propia sin reutilizar una sesión humana o el token interno del conector.

**Trabajo:** evaluar qué consumidores no pueden usar mecanismos existentes. Para ellos, emitir credenciales desde IAM vinculadas a empresa, scopes, vencimiento, hash, prefijo visible, último uso, rotación y revocación. Derivar el contexto de autorización de la credencial; no del cuerpo o query. Aplicar límites por consumidor.

**Aceptación:** secreto visible una sola vez; credencial revocada o vencida deja de autorizar según la política definida; scopes de lectura no envían mensajes; pruebas cruzadas por ID de recurso impiden acceso entre empresas. Ningún secreto operativo se almacena en el navegador del CRM.

**Aporte de la tercera revisión:** los permisos efectivos son la intersección de concesiones vigentes del servidor y alcance solicitado. Una lista de concesiones vacía deniega; nunca habilita como fallback los permisos enviados por el cliente. No incorporar credenciales comodín para elegir empresa desde el cuerpo ni aceptar un actor declarado por el solicitante como identidad autenticada.

### FK-13 — Adjuntos privados por etapas

**Problema:** mensajes con archivos quedan fuera del flujo de texto actual.

**Trabajo:** primero recibir y mostrar metadatos de tipos admitidos; después descargar a almacenamiento privado y ofrecer acceso autorizado; finalmente habilitar envío y, si se decide, extracción/transcripción para IA. Definir tipos MIME reales, tamaño, cuotas, análisis de archivos, retención y eliminación. No descargar URLs arbitrarias aportadas por un usuario ni adjuntar contenido automáticamente al agente.

**Aceptación:** archivos de otra empresa no son accesibles; formatos/tamaños rechazados generan una explicación; expiración y eliminación revocan acceso; medios no soportados muestran un estado explícito. Recepción, visualización, envío y uso por IA tienen pruebas y habilitación independientes.

### FK-14 — Preparar varias conexiones y proveedores

**Problema:** hoy la identidad de conversación depende principalmente del teléfono y hay una conexión por empresa; ampliar sin diseñar claves produciría colisiones.

**Trabajo:** solo después de confirmar la necesidad, introducir `connection_id`, límites por empresa y propiedad exclusiva de sesión por worker; definir un puerto de conexión/envío/eventos con capacidades explícitas. Mantener el adaptador actual. Migrar hilos y deduplicación antes de habilitar varias cuentas. Un segundo proveedor requiere implementación y pruebas propias.

**Aceptación:** el mismo contacto en dos conexiones no mezcla hilos ni recibos; reiniciar no abre dos propietarios de una sesión; desconectar una cuenta no afecta a la otra; permisos y consentimiento tienen alcance definido. Mientras siga una cuenta por empresa, no añadir un selector vacío al CRM.

### FK-15 — Pruebas de recuperación y operación reproducible

**Problema:** el smoke local no demuestra recuperación durable ni consistencia ante caídas del canal o servicios.

**Trabajo:** extender CI y smoke existentes con proveedor simulado, base de datos real para transacciones/triggers y fallos controlados en cada etapa. Cubrir concurrencia, aislamiento, sobrecarga, retiros, replay y migraciones. Documentar backup/restauración de datos, trabajos y sesiones privadas, separando salud de proceso, preparación del servicio y conexión del canal.

**Aceptación:** pruebas reproducen la brecha de duplicado sin recuperación antes del cambio y pasan después; se verifica caída tras envío y antes del registro sin reenvío automático ambiguo; restauración comprobada en entorno aislado; las pruebas normales no necesitan cuentas ni mensajes reales. Adjuntar resultados ejecutados al cerrar cada tarea.

**Ampliación de la segunda revisión:** comprobar importación del metadata ORM, contratos realmente validables, migraciones y arranque desde checkout limpio. Probar la ruta webhook → propuesta → autorización → worker → proveedor simulado → confirmación. Simulación, sandbox y ejecución real deben estar identificadas en cada resultado y aisladas por entorno; una simulación no consume credenciales ni cambia al proveedor real por faltar configuración. Resolver antes de declarar verde la suite completa la incompatibilidad `httpx`/`httpx2` detectada en FK-01. Mantener esa corrección en un cambio explícito de dependencias, sin copiar el árbol de dependencias de la referencia.

### FK-16 — Reconciliar documentación con la implementación

**Problema:** diferentes cortes documentales pueden describir el conector como laboratorio de una empresa por instancia mientras runtime e IAM ya ofrecen sesiones por empresa.

**Trabajo:** reconciliar [arquitectura raíz](ARCHITECTURE.md), [índice técnico](flowkron-product-docs/README.md), documentación de cada propietario y contratos. Separar implementado, parcial, reservado y propuesto. Precisar modo local/demo y límites productivos. Mantener este archivo como plan; trasladar a documentación técnica solo decisiones y capacidades adoptadas.

**Aceptación:** cada afirmación de capacidad tiene evidencia actual; rutas y nombres de headers coinciden con runtime; no se anuncia envío humano, recibos, multimedia o webhooks antes de su implementación. Enlaces comprobados y límites de publicación vigentes.

**Ampliación de la segunda revisión:** conservar guías de navegación y decisiones breves por dominio, verificadas contra imports, routers y Compose reales. Un servicio dibujado o una carpeta con solo README se etiqueta como propuesto. No duplicar instrucciones en prompts desconectados del código; ejemplos y schemas pasan los validadores existentes.

## Segunda revisión cruzada: control y ejecución del agente

### Cobertura y método

Se inventariaron los 119 archivos de la segunda referencia de Blandskron: 103 con contenido y 16 marcadores vacíos. Se revisaron sus 49 archivos Python, 40 documentos Markdown, interfaz React y estilos, configuración de Vite, dependencias, cuatro Dockerfiles y Compose. El recorrido cubrió los 24 handlers HTTP, modelos, schemas, servicios de los 12 dominios, gateway, clasificador y worker. La carpeta no contiene archivos de pruebas `test_*`.

Se analizó la sintaxis de los 49 Python mediante AST, sin importar ni arrancar esa aplicación ni leer secretos. Se comprobó aisladamente con SQLAlchemy instalado que `metadata` es un nombre reservado de sus modelos declarativos: la referencia lo declara como atributo en tres modelos importados por el backend. Esto es evidencia de un bloqueo de importación, no de una ejecución completa de su stack. No se instalaron sus dependencias ni se hicieron solicitudes a proveedores.

También se constató que faltan el `tsconfig.json` que necesita el comando `tsc` previsto y el `.env.example` que promete la guía. Los esquemas de referencia están en bloques Markdown y usan tipos JSON Schema en mayúsculas, por lo que no son contratos directamente adoptables. No se atribuye funcionalidad operativa a las instrucciones, diagramas o ejemplos que no corresponden al código.

### Qué aprender y cómo aterrizarlo en Flowkron

| Área revisada | Evidencia de la segunda referencia | Contraste con Flowkron después de FK-01 | Decisión |
| --- | --- | --- | --- |
| Separación por dominios | Modelos, schemas, servicio y router agrupados por capacidad | Ya existen propietarios separados para identidad, operación e IA | Mantener servicios actuales; usar esa separación interna al ampliar Operational |
| Acción como entidad | Tipo, argumentos, estado, resultado, error y correlación | El [schema del agente](flowkron-agent-core/app/api/v1/schemas/agent.py) enumera acciones, pero [prepare_action](flowkron-agent-core/app/infrastructure/external_tools/mock_tools.py) solo habilita `none` y `handoff_human` | FK-17: pasar de nombres reservados a propuestas y ejecución autorizada |
| Supervisión humana | Endpoint de aprobación y estado `requires_review`; el clasificador siempre propone sin revisión y el webhook crea acciones pendientes | El handoff actual marca un lead, sin bandeja de aprobación de herramientas | FK-18, enlazada a FK-06; aprobar argumentos concretos con permisos reales |
| Pausa de IA | El panel cambia un valor en DB; el webhook consulta configuración de proceso y conversación | Falta una política efectiva común para entrada, agente, trabajos y envío | FK-19: una fuente de verdad y comprobación antes de cada efecto |
| Planificar y ejecutar | La API guarda la acción; un worker procesa tipos conocidos | El conector aún genera y envía dentro del recorrido del mensaje | Ampliar FK-02/FK-03; separar decisión de efecto sin añadir otro broker por defecto |
| Colas | Publicación tras commit; `RPUSH` + `BRPOP`; sin ack, lease, recuperación ni estado final de fallo en la captura general | FK-03 ya propone outbox y recuperación | No copiar la cola; incorporar pruebas de caída, justicia y reconciliación |
| Reuniones | Registro de evento y ruta directa con código de Calendar; el worker solo crea un resultado simulado | No existe agenda operativa conectada al agente | FK-22; disponibilidad, fechas confirmadas y resultado real antes del aviso |
| Correo | Ruta directa con código de Gmail y registros de correo; el worker simula envío por separado | Ya existe [correo transaccional Blandskron](smtp-http-blandskron/README.md); no hay acción comercial del agente habilitada | FK-23: reutilizar el gateway cuando corresponda y separar identidad de remitente de la del usuario |
| Integraciones | Cuenta, token, estado y desconexión; flujo OAuth incompleto | El login Google de IAM verifica identidad; no concede permisos de correo o calendario | FK-24: autorización delegada separada del inicio de sesión |
| Sesiones del agente | Intención, confianza y snapshot registrados; confianza fija y datos de fecha/destinatario prefijados | El modo Operational es [stateless](flowkron-agent-core/app/application/orchestration/agent_runtime.py) y responde usando consulta actual/contexto; persistir chats no implica enviar su historial al modelo | FK-20 para memoria y FK-26 para trazas y evaluación |
| Leads | Contacto enlazado a acciones; clasifica como calificado por palabras clave | [Operational](flowkron-operational-service/app/services/ingest_service.py) ya crea contactos/leads y acepta clasificación | FK-21 amplía extracción confirmada; no crear otro dominio de contactos ni calificar automáticamente por una palabra |
| Notificaciones | Registros de alerta y panel lateral; servicio de entrega solo descrito en README | La [pantalla actual](flowkron-front-app-angular/src/app/domains/dashboard/features/notifications-page/notifications-page.component.ts) lista hilos que requieren humano | FK-25 amplía la pantalla con notificaciones persistentes, lectura y entregas verificadas |
| Estados visibles | Acción, error y resultado juntos en el panel; backend ONLINE fijo y estados simulados como éxito | El CRM ya tiene sus propias superficies y permisos | Integrar vistas en Angular; mostrar capacidad, origen simulado, frescura y error real, sin copiar otro frontend |
| Auditoría y configuración | Existe correlación, pero algunos cambios no auditan y varios commits fragmentan el recorrido | FK-09 y FK-16 ya cubren trazas y realidad documental | Ampliar sus criterios; la existencia de una tabla de auditoría no prueba cobertura completa |

### Límites que no se deben heredar

1. **La IA propone; el backend decide.** En la referencia los argumentos y el estado son poco restringidos y la bandera `requires_review` no llega a una política efectiva de revisión. No usar una puntuación fija de confianza como autorización.
2. **Autenticación y aislamiento son requisitos para todas las capacidades nuevas.** Los routers revisados dependen de la sesión DB sin una identidad autenticada ni scope por empresa. El webhook contempla una firma, pero su comprobación queda en un `pass`. Flowkron debe conservar IAM y la empresa resuelta por credenciales en vez de confiar en un ID enviado por la IA.
3. **Una operación guardada no equivale a ejecutada.** La respuesta del webhook guarda mensajes y notificaciones como enviados sin invocar el despacho saliente; el gateway de salida devuelve entrega simulada. El worker escribe reuniones/correos simulados aunque existan métodos de proveedor real en otra ruta. Mantener un único camino autorizado de ejecución y señalar explícitamente simulación.
4. **Los fallos pueden ocurrir después del efecto externo.** La ruta de correo referencia `settings` sin importarlo después de enviar al proveedor; si se alcanza ese punto puede registrar fallo tras un envío real. No reintentar ciegamente un efecto porque una etapa local posterior falló.
5. **OAuth necesita vinculación y ciclo de vida reales.** La referencia usa un `state` constante que el callback no verifica, guarda tokens sin cifrar aunque el campo se llame cifrado, no implementa refresh y activa/desactiva cuentas globalmente. Su enlace de conexión abre una respuesta JSON con URL; no completa por sí solo una navegación de autorización.
6. **No inventar datos para completar una acción.** El clasificador fija una fecha y un destinatario de ejemplo si faltan datos. Ante «mañana a las 10», Flowkron debe resolver contexto temporal y pedir confirmación; ante email ausente, preguntar. Los proveedores se eligen por configuración autorizada de la empresa.
7. **Los modelos necesitan validación ejecutable.** Atributos ORM reservados, schemas Markdown no validables, timestamps sin zona y ausencia de unicidad de mensaje no se corrigen con documentación. No copiar tablas ni dependencias; aprovechar la migración y las claves que ya agregó FK-01.
8. **El panel debe reflejar el recorrido real.** La referencia consulta recursos completos sin paginación; el refresco periódico no vuelve a pedir el hilo seleccionado, y hay estados saludables pintados de forma constante. Flowkron mantiene sus componentes y completa consultas, frescura y errores mediante FK-08/FK-09/FK-25.
9. **Minimizar datos también en desarrollo.** No registrar URLs de conexión con credenciales, webhooks completos, cuerpos de correo o tokens en logs generales. No usar un almacén de settings genérico para secretos ni sobrescribir decisiones del operador con defaults de arranque.
10. **La arquitectura dibujada no exige nuevos microservicios.** El runtime separado y el servicio de notificaciones de la referencia son mayormente documentación. Implementar primero módulos con propietario y contratos claros; separar procesos solo por necesidades de carga, aislamiento o operación demostradas.

### FK-17 — Propuestas de acciones tipadas y ejecución autorizada

**Problema:** Flowkron declara herramientas futuras, pero no tiene un ciclo productivo de propuesta, validación y resultado para ejecutarlas.

**Trabajo:** crear en Operational una entidad de acción vinculada a empresa, conversación, mensaje y ejecución del agente; catálogo permitido con argumentos y resultados tipados por acción. Agent Core solo propone; Operational determina identidad, permisos, alcance y política. Distinguir propuesta incompleta, pendiente de confirmación/revisión, lista, ejecutándose, completada, fallida, cancelada y resultado desconocido. Los jobs de FK-03 ejecutan una acción validada; no aceptan SQL, URLs o comandos arbitrarios generados por el modelo. Reutilizar schemas existentes cuando correspondan y versionar contratos adoptados.

**Aceptación:** herramientas desconocidas y argumentos inválidos no se ejecutan; la IA no elige empresa, remitente ni permisos; entrada repetida no crea una segunda acción lógica; cada transición conserva autor, versión y correlación. Un resultado simulado no figura como ejecución real. `create_lead` debe actualizar la lógica actual en vez de crear una segunda tabla de clientes.

**Aporte de la tercera revisión:** el catálogo de herramientas del backend define permiso, tipos de argumentos/resultado, modo consulta/escritura, integraciones requeridas y timeout efectivamente aplicado. El planner no puede rebajar esos requisitos. Separar análisis sin efectos de ejecución autorizada: nombrar una ruta `analyze` no la hace inocua si llama al mismo ejecutor. Normalizar resultados de dominio como `needs_input`, `connection_required`, `awaiting_approval`, `succeeded`, `failed`, `unknown` y `cancelled`; terminar una función sin excepción no prueba éxito de negocio. Una solicitud con varias acciones presenta resultados individuales y estado agregado honesto; no ofrece atomicidad entre proveedores ni continúa un paso dependiente después de un fallo.

### FK-18 — Revisar, aprobar y rechazar acciones desde el CRM

**Problema:** aceptar un nombre de herramienta no basta para autorizar sus efectos y actualmente no existe revisión de propuestas externas en el CRM.

**Trabajo:** bandeja Angular por empresa con resumen entendible, destinatarios, recursos afectados, argumentos exactos, motivo de revisión y resultado. Aprobar, rechazar o pedir corrección según rol. La política del backend decide qué requiere revisión o confirmación del contacto; no un campo enviado por la IA. Vincular aprobación a la versión/hash de argumentos, actor y vencimiento; todo cambio posterior invalida esa aprobación. El worker comprueba vigencia y permisos antes del efecto.

**Aceptación:** otro tenant o un lector no aprueba; doble aprobación no encola dos veces; editar destinatario después de aprobar obliga a revisar de nuevo; revocar la integración o pausar la automatización bloquea efectos pendientes. Se conserva el rechazo y su motivo. La aprobación de acciones es distinta de tomar el control del chat en FK-06.

**Aporte de la tercera revisión:** distinguir denegación por falta de permiso, argumentos incompletos, conexión ausente y revisión humana requerida. Una aprobación no concede un permiso que el solicitante no tenía ni transforma una solicitud inválida en ejecutable. La propuesta sigue identificada al expirar o reintentarse; generar un UUID de aprobación sin registro y sin transición verificable no constituye un flujo de aprobación.

### FK-19 — Control efectivo de IA y configuración por empresa

**Problema:** un toggle visible puede divergir del estado que usa el agente, especialmente con varias réplicas y trabajos pendientes.

**Trabajo:** definir política persistente y versionada por empresa/conversación, con controles de plataforma restringidos a Blandskron cuando sean necesarios. Orden de precedencia explícito: bloqueo de plataforma/empresa, retiro de consentimiento, pausa humana, configuración de herramientas y decisión del agente. Comprobarla antes de generación y ejecución/envío. Separar «pausar generación» de «cancelar efectos pendientes» y mostrar su alcance. El arranque crea defaults solo si faltan, sin sobrescribir cambios del operador. Configuración de secretos queda en el mecanismo seguro, fuera de settings públicos.

**Aceptación:** pausar desde el CRM afecta a otra réplica y al worker dentro de un límite documentado; sobreviven reinicios; la entrada sigue registrada sin respuestas automáticas repetitivas de pausa. Un trabajo iniciado antes de la pausa se revalida antes del envío. Cambios y reactivación quedan auditados; activar no revive acciones canceladas ni concede permisos nuevos.

### FK-20 — Memoria conversacional acotada y consistente

**Problema:** el historial visible no garantiza continuidad de razonamiento. El recorrido stateless de Flowkron consulta documentos con el mensaje actual y no construye un historial de turnos para el modelo.

**Trabajo:** recuperar desde Operational los últimos turnos del hilo autorizado y, cuando aporte valor, un resumen incremental versionado con procedencia. Separar contexto de empresa, datos confirmados del cliente, conversación y resultados de acciones. Limitar tokens, antigüedad y datos sensibles; tratar mensajes y documentos como información, sin permitirles cambiar las instrucciones de ejecución. Concurrencia por hilo y posición de último mensaje para evitar resúmenes que salten o dupliquen turnos. No reactivar la persistencia alterna del agente como segunda fuente de conversaciones.

**Aceptación:** «sí, ese horario» refiere a una propuesta anterior del mismo hilo; no recupera contenido de otra empresa/conexión. Reintentos usan el mismo corte de contexto cuando corresponde; un retiro o purga invalida resúmenes derivados. La simulación no escribe recuerdos en conversaciones reales y se registran límites de contexto sin guardar por defecto prompts completos.

**Aporte de la tercera revisión:** evitar guardar como «última memoria» un contexto que contiene recursivamente toda la memoria anterior. Usar estructuras planas, versiones/posiciones de turno, tamaño máximo, caducidad y resolución de escrituras concurrentes. Una etiqueta `semantic` no equivale a recuperación semántica; cada memoria debe tener una finalidad y un consumidor probado antes de persistirse. La invalidación y eliminación se coordinan con FK-27.

### FK-21 — Enriquecer leads con datos confirmados

**Problema:** hay contactos y clasificación en Flowkron, pero falta un camino conversacional trazable para completar datos sin inventar información o elevar automáticamente la calificación.

**Trabajo:** reutilizar `Cliente`, `Lead` y servicios actuales. Proponer cambios de nombre, email, interés y etapa con mensaje de origen, valores anteriores y candidatos; validar formato y pedir confirmación si hay ambigüedad o se afecta el destinatario de una acción. Distinguir dato declarado, inferido y confirmado. Mantener reglas de clasificación de negocio separadas de intención de guardar. Aplicar actualizaciones idempotentes y limitar qué campos puede sugerir la IA.

**Aceptación:** una palabra como «cliente» no califica el lead; un dato vacío o inferido no reemplaza uno confirmado; corregir el correo invalida propuestas que dependían del anterior. Operador y contacto pueden corregir datos con trazabilidad; no se crean contactos duplicados ni se mezclan personas por compartir un hilo accidentalmente.

### FK-22 — Agenda conversacional con disponibilidad y confirmación

**Problema:** coordinar una reunión es una evolución útil, pero hoy no hay herramienta habilitada ni integración de agenda operativa en Flowkron.

**Trabajo:** añadir una capacidad de agenda detrás de FK-17, con proveedor configurado por empresa y cuenta autorizada en FK-24. Extraer fecha, duración, zona, calendario y asistentes; preguntar lo que falta. Interpretar expresiones relativas usando la fecha del mensaje y la zona pertinente; validar fechas pasadas y cambios de horario. Consultar disponibilidad y revalidarla antes de crear; confirmar detalles con el contacto. Guardar ID externo y estado; permitir consultar, reprogramar o cancelar como acciones distintas. Identificar enlace de videoconferencia y enlace del evento por separado.

**Aceptación:** no se usan fechas o asistentes de ejemplo; dos reservas concurrentes conflictivas tienen una resolución explícita y no se promete bloqueo atómico si el proveedor no lo ofrece. Reintentos y resultado desconocido reconcilian el evento; cambios/cancelaciones preservan correlación. Se avisa «creada» solo con resultado comprobado; si el enlace de reunión está pendiente, se muestra como tal. La especificación del proveedor se verificará al implementar, sin asumir vigentes los permisos de la referencia.

**Aporte de la tercera revisión:** un borrador o evento guardado solo en Flowkron no es una reserva en el calendario externo. Si falta conexión, informar qué falta y conservar la propuesta; no convertir silenciosamente una solicitud externa en una reunión local ni inventar una hora para completar el proceso. Si se ofrece agenda local, será una capacidad explícita y confirmada, con estado distinto.

### FK-23 — Correo comercial vinculado a conversación

**Problema:** Flowkron tiene correo de cuentas/contacto, pero eso no habilita al agente a enviar seguimientos comerciales por petición de un chat.

**Trabajo:** definir borrador, destinatarios confirmados, remitente autorizado, asunto, contenido y aprobación como una acción. Reutilizar Correo Blandskron para envío transaccional cuando su modelo de remitentes corresponda; evaluar un adaptador de buzón delegado solo si la empresa lo necesita. Mantener política, registro de negocio y permisos en Operational, sin trasladarlos al gateway. Registrar acción, mensaje, ID de proveedor y estado; separar aceptación, entrega y rebote. Una futura lectura/respuesta del buzón requiere otro alcance y no se presupone por habilitar envío.

**Aceptación:** no se usa una dirección de ejemplo cuando falta el email; la IA no escoge remitentes ajenos ni amplía destinatarios sin validación. Un timeout queda reconciliable; no duplica envío al fallar el registro local. Distingue identidad de login y autorización del buzón. Los correos automáticos comerciales no se habilitan por el consentimiento de registro de cuenta; aplicar la política de finalidad/canal definida por la empresa.

**Aporte de la tercera revisión:** mostrar datos pendientes y conexión pendiente como causas distintas. El proveedor/remitente es parte de la propuesta autorizada: no cambiar de un buzón delegado al remitente de infraestructura al faltar o vencer la conexión, salvo una política explícita y una aprobación todavía válida para ese destino. Registrar el resultado real del proveedor como dato de negocio, no envolver `connection_required` en un éxito genérico del ejecutor.

### FK-24 — Integraciones delegadas y credenciales por empresa

**Problema:** iniciar sesión con Google identifica un usuario; no autoriza automáticamente a operar su calendario o correo ni establece qué cuenta pertenece a cada empresa.

**Trabajo:** modelo de integración por empresa, proveedor, cuenta externa, scopes realmente concedidos, estado, vencimiento y responsable. Flujo OAuth con vinculación de sesión/empresa, `state` aleatorio de un solo uso, expiración, validación de callback y PKCE cuando corresponda; secretos cifrados con rotación y refresh coordinado. Comprobar requisitos actuales en documentación oficial durante la implementación. Estados distintos para no configurado, simulado, conectado, expirado, revocado y error. Desconectar una cuenta no desactiva cuentas de otras empresas; revocar tokens y trabajos pendientes conforme al alcance concedido.

**Aceptación:** callback con estado repetido, vencido o de otra sesión se rechaza; ningún token se devuelve al navegador ni aparece en logs; dos workers no corrompen la renovación. Falta de scopes bloquea solo la capacidad afectada. Conexión/desconexión y cambio de cuenta requieren permiso y auditoría; pruebas con proveedor simulado verifican revocación y aislamiento antes de habilitar sandbox o cuentas reales.

**Aporte de la tercera revisión:** exponer un catálogo mínimo de capacidades por empresa, con permiso efectivo y preparación de la integración, sin secretos. Permite al CRM explicar qué conectar o completar antes de solicitar una acción. Consumir `state` y renovar credenciales requieren coordinación transaccional; leer «no usado» y actualizar después sin exclusión no garantiza un solo uso. Devolver el identificador persistido de la conexión, sin fabricar otro en cada respuesta de configuración.

### FK-25 — Centro de notificaciones de negocio y entregas

**Problema:** la pantalla actual indica atención humana, pero no agrupa resultados pendientes, solicitudes de aprobación o fallos de integraciones con un estado propio de lectura y resolución.

**Trabajo:** ampliar la experiencia existente con notificaciones persistentes por empresa/destinatario y referencias a conversación, acción y trabajo. Preferencias por tipo y canal, lectura/resolución, agrupación para evitar tormentas y política de reintentos. Crear la notificación en la transacción del resultado y sus entregas como trabajos de FK-03. Confirmaciones de cliente dependen de resultados de negocio comprobados; alertas internas no exponen conversaciones completas ni usan un destino global compartido entre empresas.

**Aceptación:** una caída del correo no pierde el resultado de negocio; la alerta interna permanece visible. Crear el registro no lo marca entregado; cada canal tiene su propio estado. Usuarios solo ven sus avisos autorizados, cambios de destinatario no reenvían datos antiguos sin política y un resultado repetido no genera avisos duplicados. Abrir el aviso lleva al recurso existente con el contexto correcto.

### FK-26 — Evaluación del agente, trazas y presupuestos

**Problema:** una confianza de clasificación o un score de recuperación no mide por sí solo la corrección de una respuesta o la seguridad de una acción. El modo Operational tampoco hereda automáticamente las trazas de la persistencia local del agente.

**Trabajo:** conjunto versionado de casos sintéticos en español para contexto, seguimiento de turnos, datos faltantes, negaciones, fechas, correcciones, handoff e intentos de manipular herramientas. Medir exactitud de extracción/acción, derivación adecuada, afirmaciones sin evidencia, latencia y consumo cuando el proveedor lo reporte. Registrar versión de modelo, prompt, política, documentos y ejecución; persistir trazas mínimas en Operational. Presupuestos por empresa, límites de contexto y concurrencia; distinguir consumo observado, estimado y desconocido. Reutilizar el simulador como comparación antes de habilitar una nueva versión, sin enviar efectos reales.

**Aceptación:** cambiar prompt/modelo ejecuta casos reproducibles con umbrales acordados; «no envíes correo» no dispara un envío por coincidir con una palabra. Una baja puntuación deriva o pregunta según política; no se anuncia como probabilidad calibrada. El simulador informa qué propondría y por qué sin ejecutar. Límite excedido produce un resultado comprensible y trazable, no un cobro o envío oculto. Costos usan tarifas verificadas al implementar y muestran fecha de estimación.

**Aporte de la tercera revisión:** pruebas de ausencia de efectos al analizar/simular; denegación ante concesiones vacías aunque el cliente pida permisos; resultados de negocio fallidos aunque el HTTP sea 200; timeout aplicado de verdad y ninguna ejecución tardía oculta. Probar que la respuesta usa los resultados observados y no solo cuenta acciones propuestas. Medir tamaño de memoria tras muchos turnos y verificar que se mantiene acotado.

## Tercera revisión cruzada: selección de aportes de tres POC

### Cobertura y criterio de selección

Se revisaron tres ejemplos locales: dos variantes de un agente empresarial portable (78 archivos cada una, 57 Python por variante) y un panel Django de lectura de CRM (70 archivos, 34 Python). La comparación archivo por archivo de las dos variantes, normalizando el nombre de su paquete, resultó idéntica en los 78 archivos: no se cuentan como dos implementaciones independientes ni como validaciones adicionales.

Se inspeccionaron orquestación, políticas, permisos, herramientas, aprobaciones, memoria, auditoría, eventos, OAuth, correo, agenda, modelos, SDK y pruebas declaradas; para el panel, vistas, modelos y router de DB, pipeline, solicitudes de privacidad y registros de limpieza. La revisión es estática y selectiva por responsabilidad: no se arrancaron los POC, no se ejecutaron sus herramientas ni se probaron proveedores o bases reales. Posteriormente el usuario eliminó `ejemplos/`; se verificó su ausencia antes de la publicación solicitada. No se integra su código a Flowkron.

El valor incremental está en mejorar contratos de ejecución y cerrar el ciclo de privacidad. La arquitectura de agentes, correo, agenda, IAM, memoria y notificaciones ya tiene tareas en Flowkron: se agregan criterios a esas tareas, no proyectos paralelos ni diez funcionalidades repetidas.

| Evidencia de los ejemplos | Qué aporta | Aplicación en Flowkron |
| --- | --- | --- |
| Registro de herramientas con nombre, permiso y timeout; separación planner/política/ejecutor | Un catálogo explícito ayuda a validar y mostrar capacidades; en el POC el timeout se declara pero no lo impone el registro | FK-17/FK-24: requisitos del lado servidor y límites ejecutables |
| `chat`, `analyze` y `execute` llaman al mismo orquestador, que ejecuta herramientas | El nombre del endpoint no garantiza ausencia de efectos | FK-17/FK-26: análisis y simulación con prohibición verificable de escritura/envío |
| El ejecutor devuelve éxito si la herramienta retorna un objeto, incluso con resultado `connection_required`; el orquestador conserva éxito global ante errores individuales | Separar resultado del transporte, del ejecutor y del negocio | FK-17/FK-22/FK-23: estados tipados, resultados parciales y explicación veraz |
| Los permisos persistidos se intersectan con los solicitados, pero una lista persistida vacía cae a los permisos del cuerpo | El alcance solicitado solo puede reducir una concesión, nunca crearla | FK-12/FK-18/FK-26: denegar sin concesiones y revalidar identidad/permiso |
| Memoria por empresa y sesión; el contexto guardado incluye la memoria previa anidada | El scope es útil; copiar el árbol anterior hace crecer el almacenamiento/contexto sin límite | FK-20: resumen plano y acotado, control de concurrencia y borrado de derivados |
| OAuth persiste estado con expiración y ofrece refresh; el consumo es una lectura seguida de actualización y las credenciales quedan en JSON | Hay ideas de ciclo de vida, pero no garantizan exclusión concurrente ni cifrado | Completar criterios de FK-24, sin copiar almacenes o credenciales |
| El correo señala conexión ausente; la agenda puede crear un evento local cuando falta el proveedor externo | Explicar preparación de la integración y distinguir intención local de efecto externo | FK-22/FK-23/FK-24: capacidades explícitas y sin sustitución silenciosa de proveedor |
| El panel muestra consentimiento, solicitudes, fechas de resolución y contadores de limpieza sobre modelos externos `managed=False` | Visibilidad operativa de privacidad; las vistas son de lectura y no resuelven solicitudes | Nueva FK-27 sobre los modelos y APIs que Flowkron ya tiene |
| El pipeline del panel mezcla temperatura y etapa: un lead nuevo caliente también aparece en Inicio | No confundir clasificación con avance operativo ni duplicar tarjetas para aumentar métricas | Conservar el [pipeline actual de Flowkron](flowkron-front-app-angular/src/app/domains/leads/features/workflows-page/workflows-page.component.ts), que separa progreso y temperatura; no crear otro tablero por este ejemplo |

### Qué se descarta por falta de valor adicional

- Otro frontend, login por API key o acceso directo del navegador/panel a la DB: Flowkron ya tiene Angular, IAM y APIs por empresa. La intención de lectura de un router o `managed=False` no sustituye permisos de DB ni autorización por recurso.
- Facturas, cobranzas y un nuevo dominio ERP solo por aparecer en un POC. No hay un consumidor o necesidad de Flowkron demostrados para ese alcance.
- Un servidor MCP o SDK publicados: los ejemplos ofrecen un manifiesto y clientes mínimos; no prueban un protocolo completo ni justifican distribución/mantenimiento sin un consumidor concreto.
- Un motor genérico de workflows porque un método devuelve `scheduled`. El ejemplo no programa ni ejecuta esos pasos. La recuperación de trabajos sigue en FK-03; las acciones autorizadas, en FK-17.
- Más categorías de memoria, eventos en listas locales o métricas de proceso como si fueran infraestructura durable/distribuida. Se conserva la dirección existente de FK-03/FK-09/FK-10/FK-20.
- Copiar plantillas que convierten datos de clientes en HTML mediante cadenas, defaults de acceso del prototipo o generación de migraciones en cada arranque. La apariencia y las instrucciones del POC no sustituyen las verificaciones de runtime de Flowkron.

### FK-27 — Resolver solicitudes de privacidad y verificar retención

**Problema:** Flowkron registra solicitudes y permite [leer solicitudes y logs de limpieza](flowkron-operational-service/app/api/v1/operational.py), pero ese registro no implementa el circuito de verificación, resolución, exportación o eliminación. El [modelo activo](flowkron-operational-service/app/tenant_models/operations.py) ya tiene `SolicitudDerecho`, `LogLimpieza` y campos de consentimiento; crear otras tablas de clientes o un portal separado duplicaría la base existente.

**Trabajo:** completar el flujo en Operational y CRM: solicitud, verificación del solicitante y alcance, responsable, decisión autorizada, trabajo de ejecución y resultado comprobable. Separar retirada de consentimiento de solicitud de acceso/exportación, rectificación, oposición o supresión. Definir política de retención por tipo de dato y plazos configurables; verificar requisitos aplicables al implementar/desplegar, sin tratar el default técnico de 30 días como una garantía normativa.

Inventariar mensajes, respuestas preparadas y turnos FK-02, trabajos, adjuntos, datos de contacto, contexto/memoria derivada e integraciones que hayan recibido datos. Coordinar cancelación o bloqueo con FK-03/FK-04 antes de borrar. Prever supresión o seudonimización de identificadores de deduplicación según una política explícita para que un replay no recree automáticamente el contacto eliminado. Las exportaciones usan selección autorizada y acceso privado con vencimiento; no se entregan dumps de la empresa ni se envían datos al LLM para resolver la solicitud por defecto.

**Aceptación:** solo roles autorizados gestionan solicitudes y cada operación queda limitada a su empresa/persona verificada. Reintentar no duplica exportaciones o borrados. Se prueba una eliminación con un turno preparado, un envío en curso, adjuntos y memoria derivados; se informa qué ya fue enviado externamente y qué exige gestión adicional, sin prometer cancelación retroactiva. Los logs conservan evidencia mínima de decisión/ejecución sin volver a almacenar el contenido eliminado. Un fallo parcial queda pendiente con alcance y motivo; marcar «completada» requiere verificar cada almacén previsto. Restaurar un backup aplica la política de supresión antes de reabrir tráfico y no reintroduce datos sin control; se declaran límites y caducidad de copias en lugar de afirmar que desaparecieron inmediatamente.

**Relación con el plan:** FK-04 evita nuevos efectos tras retirar autorización; FK-27 gestiona la solicitud y el ciclo de vida de datos. FK-13 aporta tratamiento de archivos y FK-20 el de memorias derivadas cuando esas capacidades estén presentes. No requiere implementar todas las funciones futuras para resolver solicitudes sobre los datos actuales.

## Orden recomendado y límites de ejecución

1. **Integridad:** FK-01 → FK-02 → FK-03, con FK-04 y pruebas FK-15 desde el inicio. FK-05, FK-09 inicial y FK-16 pueden avanzar sin esperar nuevas funciones.
2. **Operación:** FK-06, FK-07 y FK-08. Entregar un circuito completo de atención, evitando una pantalla que solo simule respuestas.
3. **Extensibilidad:** FK-10 → FK-11; FK-12 cuando haya consumidores concretos. FK-13 como entregas separadas. FK-14 queda condicionada a necesitar múltiples conexiones o proveedores.
4. **Agente supervisado:** avanzar FK-19 y FK-20 sobre la base recuperable; FK-26 acompaña sus entregas. FK-17 → FK-18 habilita acciones de negocio con política; FK-21 y FK-25 completan datos confirmados y supervisión.
5. **Servicios al cliente:** FK-24 habilita cuentas delegadas; después FK-22 y FK-23, empezando por proveedores simulados y sandbox. La agenda y el correo no deben adelantarse a recuperación, permisos o confirmación de argumentos.
6. **Ciclo de datos:** diseñar FK-27 junto con FK-03/FK-04 y entregarla sobre los almacenes actuales; ampliar su cobertura al incorporar archivos, memoria e integraciones. El análisis de los tres POC no altera la prioridad inmediata de FK-03.

No hay fechas de entrega asignadas. La instrucción posterior del usuario inició FK-01; las demás mejoras requieren continuar sus tareas. Se autorizó commit y push del trabajo acumulado. No se conectaron cuentas reales, desplegaron servicios ni migraron bases existentes.

## Cierre de esta revisión

- [x] Comparar implementación previa y Flowkron, separando código real de declaraciones.
- [x] Conservar aprendizajes como tareas con evidencia, responsables técnicos, dependencias y aceptación.
- [x] Mantener las propuestas dentro de los límites actuales de Flowkron.
- [x] Retiro de la primera referencia: el usuario eliminó la carpeta y se verificó su ausencia en esta segunda revisión.
- [x] Segunda revisión completa y conservación de aprendizajes en FK-17 a FK-26 y ampliaciones de FK-02/FK-03/FK-06/FK-09/FK-15/FK-16.
- [x] Tercera revisión de tres POC: detectar variantes equivalentes, incorporar mejoras concretas a ocho tareas existentes y añadir solo FK-27 como capacidad nueva.
- [x] Retirar la segunda carpeta de referencia después de conservar el análisis; ausencia verificada en el workspace.
- [ ] Ejecutar tareas de evolución en cambios posteriores.

Los aprendizajes quedan conservados aquí. No se incorpora código, configuración, dependencias ni activos de las referencias a Flowkron; las mejoras futuras se implementan en los componentes propietarios existentes.

La tercera revisión conserva 27 tareas consecutivas, enlaces locales existentes, UTF-8 y ausencia de nombres de las referencias. La instrucción posterior solicita una tarea pequeña y publicar todo en `main`: se entrega la corrección acotada de FK-09 junto con FK-02 y el análisis acumulado. Los POC no forman parte del commit. No se aplican migraciones a la instalación ni se despliegan servicios por hacer push.
