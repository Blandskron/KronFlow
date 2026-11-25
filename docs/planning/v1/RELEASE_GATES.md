# Gates de release Community v1

**Estado actual:** código Community v1.0 y POST-v1 implementado (`tenant_schema_v16`), pendiente de corrida final de release en CI. Registrar por gate SHA, fecha, entorno, responsable, comando o recorrido, resultado y enlace a evidencia. Un fallo P0, una omisión de un gate requerido o un canal anunciado sin evidencia impiden la promoción. [Alcance](FINAL_SCOPE.md) · [Readiness](../../../RELEASE_READINESS.md)

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

## Gates externos pendientes para producción

Todo el alcance funcional v1.0 y POST-v1 (`tenant_schema_v16`) está implementado y verificado en CI ([Validate `45222208571`](https://github.com/Blandskron/KronFlow/actions/runs/45222208571)). Restan únicamente dos comprobaciones operativas externas antes de etiquetar una release estable en producción:

| Ticket | Evidencia actual | Falta para cerrar |
| --- | --- | --- |
| FK-14 | Conexión de laboratorio y recibos ejercitados con stubs | Validación de vinculación y reconexión con cuentas reales autorizadas y aislamiento por conexión |
| FK-15 | Upgrade sintético v3–v16, rollback transaccional y restore cifrado de Operational | Validate y Compose sobre el SHA candidato, restauración de toda la instalación y medición de recuperación |
