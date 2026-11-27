# Alcance congelado propuesto de Community v1.0

El [registro de trazabilidad](TRACEABILITY.md) y el [changelog](../../../CHANGELOG.md) documentan el alcance implementado (`tenant_schema_v21`). La promoción a release estable exige completar los [gates de release](RELEASE_GATES.md) y [readiness](../../../RELEASE_READINESS.md).

| Prioridad | Capacidad | Evidencia de aceptación y límite |
| --- | --- | --- |
| MUST | Instalación estándar y demo reproducibles | Checkout limpio, inicio sin proveedor opcional, alta y provisioning de empresa, persistencia tras reiniciar. Demo usa datos sintéticos. |
| MUST | IAM, seguridad y ciclo de datos | Sesión y permisos comprobados, aislamiento por recurso, rollover de llaves y suspensión efectiva. Ensayo de backup/restore, upgrade y gestión de solicitudes sobre almacenes activos. |
| MUST | Contactos y captura | Contacto canónico, evidencia de propósito, deduplicación y una captura por formulario o integración acotada. Inbox y conversación respetan el estado del canal. |
| MUST | Atención y ventas | Inbox con control humano/IA, respuesta y resolución sintética. Oportunidad persistente con etapa, responsable y resultado. Propuestas de IA limitadas a efectos autorizados. |
| MUST | Campañas email | Plantilla, audiencia, aprobación, envío de prueba, baja y recibos durables. Un release que anuncie email real requiere configuración autorizada y evidencia de aceptación y entrega. |
| MUST para anunciarlo | Campañas WhatsApp real | Adaptador autorizado, opt-in y plantillas del canal, baja y recibos verificados. Si estos gates faltan, publicar alcance email con WhatsApp de campañas deshabilitado y demo sintética. Baileys permanece como laboratorio inbound. |
| MUST | Analítica, UX y docs | KPIs reproducibles con cobertura explícita, onboarding local, documentación navegable, acciones disponibles según permisos y estado de proveedor. |
| SHOULD | Mejoras acotadas | Importación/exportación y fusión, segmentos dinámicos, memoria acotada, enriquecimiento confirmado, revisión avanzada, notificaciones y cuentas delegadas adicionales. Se publican solo con gates propios completos. |
| POST-v1 | Extensiones | Agenda avanzada, adjuntos extensos, webhooks genéricos para terceros, omnicanal extenso, automatizaciones multietapa, atribución y analítica avanzada. |

Un cambio de alcance MUST requiere evidencia de un bloqueo funcional, de seguridad o de release. Registrar decisión, dueño y efecto sobre los gates antes de incluirlo. Las funciones opcionales tienen estado visible en configuración y en la guía de instalación. [Gates de release](RELEASE_GATES.md) · [Trazabilidad](TRACEABILITY.md)
