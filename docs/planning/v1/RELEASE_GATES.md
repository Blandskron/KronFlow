# Gates de release Community v1

**Estado inicial:** source preview. Registrar por gate SHA, fecha, entorno, responsable, comando o recorrido, resultado y enlace a evidencia. Un fallo P0, una omisión de un gate requerido o un canal anunciado sin evidencia impiden la promoción. [Auditoría de seguridad y calidad](07-security-quality-release.md) · [Alcance](FINAL_SCOPE.md)

| Gate | Comprobación y evidencia Go | Responsable |
| --- | --- | --- |
| F1 · CI de Operational | Validate en el SHA candidato. En Operational verificar binarios PG, suite completa, OpenAPI, código y audit. Solo se permite omitir el benchmark del inbox en el job funcional. | Operational + CI |
| F1 · upgrades | Restaurar fixtures de versiones v3–v8 en DB descartable. Aplicar migración actual dos veces, comprobar referencias, constraints y ausencia de efectos repetidos; ensayar rollback y considerar runtimes suspendidos. | Operational + Deploy |
| F2 · CRM y aislamiento | Ejecutar recorridos sintéticos de dos empresas con IDs coincidentes, captación, contacto, consentimiento, handoff y cierre comercial. Verificar roles efectivos y revocación en operaciones sensibles. | IAM + Operational + CRM |
| F3 · entrega | Ejecutar recorrido stub con aprobación, baja concurrente, pausa, reinicio y resultados inciertos. Validar cada proveedor anunciado con la evidencia del sandbox autorizado y recibos. | Operational + Canales |
| F4 · coherencia y UX | Reconciliar métricas, ejecutar builds y Playwright, y validar documentación, accesibilidad y pantallas con 401, 403 y degradación de proveedor. | CRM + Landing + Operational |
| F5 · arranque reproducible | `docker compose -f compose.yaml -p flowkron-smoke up --build --wait` y `python flowkron-deploy/bootstrap/smoke.py flowkron-smoke --standard` en entorno descartable. Repetir por separado con `compose.demo.yaml` y smoke sin `--standard`. Guardar estado y desmontar el proyecto de prueba. | Deploy |
| F5 · seguridad y distribución | Validate, dependencias y secret scan verdes. Auditar puertos, orígenes, credenciales y licencias de artefactos reales. Revisar excepción de desarrollo antes de su vencimiento y emitir notices donde corresponda. | CI + Deploy |
| F5 · operación y datos | Ensayar backup cifrado y restore aislado, rotación y permisos, retención y eliminación, observabilidad, throughput y p95 al volumen declarado. Registrar límites, RPO/RTO y prueba de recuperación. | Deploy + IAM + Operational |

**Go para RC:** entregar F1–F5 con pruebas sintéticas, instalación, restore y un alcance explícito para proveedores todavía deshabilitados. **Go para estable:** agregar evidencia operativa y de proveedores habilitados, completar privacidad y redistribución y actualizar guías con los límites medidos. Si un canal no pasa su gate, excluirlo de la disponibilidad anunciada o mantener la etapa previa según los mínimos de alcance. [Readiness vigente](../../../RELEASE_READINESS.md)

## Trabajo en curso por verificar

El inventario y las guías de source preview se reconciliaron en FK-16. El [backlog](../../../EVOLUCION_FLOWKRON.md#backlog-canónico) conserva el alcance de los tickets pendientes.

| Ticket | Evidencia actual | Falta para cerrar |
| --- | --- | --- |
| FK-03 | Cola persistente y recuperación de turnos WhatsApp | Outbox de acciones con reintento idempotente y verificación de efectos |
| FK-04 | Baja de WhatsApp, orden de consentimiento, historial en la ficha y evaluación sintética por canal y finalidad | Persistir evidencia y consultarla en la misma transacción que autoriza cada envío |
| FK-06 | Handoff visible en Bandeja y Notificaciones | Reclamar con un único responsable, responder con stub, resolver y devolver control |
| FK-09 | Resumen consistente con Bandeja, actividad diaria y propagación de correlación en las llamadas de contexto | Correlación del resto de los canales y KPIs calibrados sobre eventos durables |
| FK-10 | Proyección histórica versionada de eventos seleccionados con filtro por empresa y correlación | Persistencia de eventos de dominio con replay hacia delante, checkpoints y suscripciones por empresa |
| FK-12 | IAM dispone de credenciales y ciclo de rotación | Scope `leads:create` emitido y revocado, con verificación de expirada y ajena en Operational |
| FK-14 | Conexión de laboratorio y recibos ejercitados con stubs | Validación de vinculación y reconexión con cuentas autorizadas y aislamiento por conexión |
| FK-15 | Upgrade sintético v3–v8, rollback transaccional y restore cifrado de Operational | Validate y Compose sobre el SHA candidato, restauración de toda la instalación y medición de recuperación |
| FK-17 | Agent Core prepara propuestas sin ejecutar efectos | Ejecutor tipado con permiso al ejecutar, idempotencia y auditoría asociada |
| FK-19 | Turnos y consentimiento controlan la admisión actual | Política de empresa y conversación que bloquee nuevos permisos de IA al asumir control humano o suspender |
| FK-20 | Contexto del runtime y persistencia local de prueba | Memoria operativa acotada por conversación, con prueba de origen y retención |
| FK-21 | Captura y edición manual de información en CRM | Confirmación y aplicación de datos propuestos con origen y control de conflicto |
| FK-24 | Gateway de correo y validación sintética | Conexión y remitente delegado por empresa, sandbox autorizado, rotación y revocación |
| FK-25 | Cola de atención e historial de derivaciones persistidas | Entregas externas con permisos, deduplicación y recibos |
| FK-26 | Dataset aislado, presupuesto por solicitud y métricas informadas por el proveedor | Evaluación semántica, trazas integradas y medición de coste por empresa |
| FK-27 | Bandeja y registro auditado de revisión y cierre | Ejecución de solicitudes, verificación de retención y tratamiento de copias |
| FK-28 | Directorio, alta manual, edición y plan de backfill | Identidad multicanal persistente y captura por formulario o credencial acotada |
| FK-30 | [Reevaluación sintética de destinatarios](04-campaigns.md#prueba-local-de-elegibilidad-por-destinatario) al aprobar y despachar | Plantillas, aprobación y snapshot persistidos, worker con stub, recibos y habilitación por canal |
