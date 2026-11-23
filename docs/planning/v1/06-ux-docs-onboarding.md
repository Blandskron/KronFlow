# UX, portal documental y onboarding local

**Estado:** especificación propuesta. Se conservan Angular, el sistema visual y la marca Flowkron by BLANDSKRON. La [auditoría 01](01-audit.md#rutas-angular-activas) identifica rutas, componentes, endpoints y permisos. La secuencia propuesta se apoya en los [recorridos CRM](03-inbound-crm.md), [campañas](04-campaigns.md) y [métricas](05-analytics.md).

## Páginas y criterios de aceptación

| Pantalla o ruta | Base reutilizable y cambio mínimo | Resultado verificable |
| --- | --- | --- |
| `/login`, `/registrarse`, `/forgot-password`, `/confirm-email`, `/reset-password` | Mantener páginas IAM y estados de recuperación. Exponer estado de verificación, expiración y reintento con mensajes accionables. | Acceso, alta y recuperación navegables con teclado, errores claros y redirección a onboarding cuando corresponde. |
| `/onboarding/company` | Mantener alta de empresa y dar estado de provisioning. Continuar al espacio activo con pasos opcionales guardados por empresa. | Una recarga durante provisioning conserva estado. El flujo de primera instalación llega al dashboard sin configurar un proveedor. |
| `/app/home` y `/app/analytics` | Reutilizar shell, tarjetas y filtros. Mostrar estado de configuración y KPIs con fecha, cobertura y unidades. | Datos faltantes y denominador cero se distinguen de un conteo cero. Dos empresas devuelven datos separados. |
| `/app/contacts` | Directorio de lectura con búsqueda, paginación e indicadores de carga. Quedan propuestos el detalle, la evidencia de consentimiento y la exportación. | Búsqueda y paginación funcionan contra el servidor. Al añadir exportación, debe quedar restringida por permiso y los conflictos de identidad deben llevar a revisión. |
| `/app/conversations` | Reutilizar mensajes, cursor y lectura compartida. Añadir reclamar, responder, devolver a IA y resolver cuando la API los soporte. | El CRM muestra control humano efectivo y estados en cola, confirmados e inciertos. Dos agentes que reclaman observan el ganador y recargan el estado. |
| `/app/workflows` | Mantener entrada de navegación; sustituir la derivación actual por oportunidades persistentes cuando exista el contrato. | Mover etapa con teclado o control alternativo al arrastre; un conflicto de versión conserva el estado de servidor y ofrece recargar. |
| Campañas y plantillas, rutas propuestas | Editor con vista previa, audiencia, canal habilitado y acciones según permiso. Exponer borradores, revisión y resultados. | El envío de prueba de demo se distingue del real. Un canal sin credenciales y gates aprobados explica el requisito sin abrir una ruta de envío. |
| `/app/business-context` | Reutilizar carga de documentos y simulador. Separar configuración del agente y estado persistente, según modo soportado. | Archivo inválido, error de procesamiento y falta de permiso mantienen feedback. El simulador muestra modo demo o proveedor. |
| `/app/whatsapp` y alias `/app/integrations` | Reutilizar diagnósticos, QR y estados de conexión. Incorporar credenciales acotadas solo al disponer de una API habilitada. | QR vencido desaparece. Las acciones de vinculación dependen de `whatsapp.connect` y de una empresa activa. |
| `/app/notifications` | Mantener handoffs como lista. Incorporar historial solamente al habilitar FK-25. | Se distingue alerta pendiente de historial y se navega a la conversación aún accesible. |
| `/app/settings` | Reutilizar perfil, miembros, invitaciones y ciclo de empresa. Usar autorización de IAM para cada acción. | Roles, últimos propietarios, suspensiones y errores de invitación tienen estado explícito. |
| Landing `/` y `/politica-privacidad` | Preservar CTA actuales, contacto institucional y aviso de privacidad. Agregar navegación de documentación y enlace al onboarding. | Enlaces validados en un checkout limpio y formulario operativo con error, éxito y protección CSRF. |

Reutilizar `dashboard-shell`, navegación, `ThemeToggleComponent`, estilos y servicios de datos tipados. Cada vista debe cubrir carga, vacío, error recuperable, acceso denegado y acción en curso. Probar tabulación, foco visible, lectores de pantalla para avisos, contraste claro/oscuro y recorte a 320 px. Mantener HTML semántico y etiquetas específicas. El servidor conserva la autorización y la UI adapta disponibilidad con respuesta del backend. [Shell actual](../../../flowkron-front-app-angular/src/app/domains/dashboard/features/dashboard-shell/dashboard-shell.component.html) · [Pruebas visuales CRM](../../../flowkron-front-app-angular/tests/visual/flowkron-front.visual.spec.ts) · [Pruebas landing](../../../flowkron-front-landing-angular/tests/visual/flowkron-landing.visual.spec.ts)

## Onboarding propuesto

1. Crear y verificar cuenta; en modo estándar local, consultar el correo de verificación en la consola privada cuando se use el backend de consola. Crear empresa y confirmar que IAM terminó el provisioning de Operational.
2. Mostrar entorno local, demo o instalación configurada. Ofrecer contexto empresarial y canal como pasos opcionales. Mantener un estado explícito de configuración y enlazar al diagnóstico correspondiente.
3. Importar o crear contacto cuando exista el contrato. Proporcionar captura sintética y simulación para observar el primer lead, atención y handoff. Evitar formularios que den por concedido consentimiento comercial.
4. Completar prueba de campaña solo con el stub o proveedor de prueba autorizado. Mostrar nombre del canal, entorno y resultado de disponibilidad antes de pedir datos. Permitir omitir los pasos opcionales y retomarlos desde el inicio.

## Portal de documentación

| Sección | Fuente y alcance |
| --- | --- |
| Producto y demo | `README.md`, alcance y recorridos comprobados; capturas de CI o entornos sintéticos sin credenciales. |
| Instalación y actualización | README, runbooks de Deploy y Operational. Variables desde `.env.example`, procedimiento de migración, restauración y rollback. |
| Funciones y seguridad | Guías por rol para contactos, inbox, oportunidades y campañas al habilitar sus contratos. Seguridad, privacidad y límites de proveedor desde documentos propietarios. |
| API y contribución | Reference OpenAPI versionada, ejemplos sintéticos y guía de contribución. Enlaces que validan desde el portal y navegación por versión. |
| Troubleshooting | Health, puertos ocupados, init, correo local, QR, migración y errores comunes con evidencia y acciones. |

La landing puede indexar páginas públicas con metadatos, canonical y sitemap. El CRM autenticado queda fuera de indexación. Un asistente documental queda para una etapa posterior y requeriría recuperar referencias versionadas y citar su fuente. [Contratos](../../../flowkron-api-contracts/README.md) · [Contribución](../../../CONTRIBUTING.md) · [Seguridad de Deploy](../../../flowkron-deploy/docs/SECURITY.md)

## Checklist de instalación y aceptación E2E

- [ ] Verificar un checkout nuevo en Linux y Docker Desktop Windows/macOS. Ejecutar las variantes estándar y demo por separado porque comparten puertos predeterminados. El job de init genera credenciales y usa volúmenes. Mantener overrides privados cuando el operador configure proveedores. [README](../../../README.md)
- [ ] Revisar `docker compose config --quiet` y `docker compose -f compose.demo.yaml config --quiet`. Comprobar que DB/Redis se mantienen en su red, qué puertos expone el frontend y qué servicios requieren credenciales opcionales.
- [ ] En un entorno descartable ejecutar `docker compose up --build --wait` para estándar y `docker compose -f compose.demo.yaml up --build --wait` para demo. Verificar health y persistencia tras parar y volver a levantar. En upgrades, ensayar backup, restauración y migración v8+ antes de habilitar conectores.
- [ ] Ejecutar el [smoke estándar y demo](../../../flowkron-deploy/bootstrap/smoke.py), Playwright para rutas y los recorridos nuevos contra API controlada. Confirmar alta, login, documentos y simulación de demo. Agregar una prueba real E2E por cada módulo habilitado con datos sintéticos y ejecutar además la matriz responsive/teclado.

Resultado esperado de v1. La instalación local llega a un CRM utilizable sin cuentas externas. Las capacidades reales de proveedor se habilitan después de validar su configuración. La UI y la documentación reflejan las capacidades comprobadas del release.
