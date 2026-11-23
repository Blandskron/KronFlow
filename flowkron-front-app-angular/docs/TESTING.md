# Testing

## Estado actual

No hay specs unitarios Angular, runner ni target `test` en `angular.json`. Aunque `package.json` contiene `"test":"ng test"`, el comando falla con `Cannot determine project or target for command`.

El único spec Playwright, `tests/visual/flowkron-front.visual.spec.ts`, valida:

- `/` redirige a `/login`;
- headings/texto de login;

Los casos de WhatsApp, Bandeja, Contactos y Seguimiento de leads sustituyen las APIs por respuestas sintéticas. Se comprueban búsqueda, paginación, navegación y marcas de lectura. El CRM cubre reintentos de ficha y actividad, conflictos de nombre y etapa, distinción entre acceso denegado y un fallo recuperable, restauración de filtros con el historial y salida de una página vacía tras guardar. El login público conserva su captura de render. Los casos usan stubs de proveedores y credenciales sintéticas.

El caso de Analytics usa un viewport móvil y verifica el corte parcial, los días con ceros, la distribución sin denominador, el cambio de zona y la recuperación con teclado después de un filtro inválido. El resumen sigue disponible si falla el reporte diario.

El recorrido manual de seguimiento tiene un [checklist con fixture para la demo](../../docs/planning/v1/MANUAL_CRM_QA.md). En Chromium se comprueban con API simulada el alta desde el contacto, la recarga tras un conflicto, el historial, el retorno al listado con filtro y la vista de solo lectura.

El caso de alta de contactos comprueba validación del teléfono, repetición de la misma solicitud tras una confirmación incierta, recuperación de datos concurrentes y enlace al seguimiento. El checklist permite crear el contacto desde la interfaz.

El [recorrido de Notificaciones](../../docs/planning/v1/MANUAL_NOTIFICATIONS_QA.md) cubre las vistas Pendientes e Historial. Chromium comprueba navegación por teclado, paginación, recuperación tras un fallo, acceso denegado y destinos que ya no están disponibles.

La [prueba manual de privacidad](../../docs/planning/v1/MANUAL_PRIVACY_QA.md) cubre la separación entre lectura, revisión y cierre. Chromium comprueba el filtro de estado, la confirmación y la vista de solo lectura.

El [recorrido de auditoría](../../docs/planning/v1/MANUAL_AUDIT_QA.md) permite recuperar un cambio de etapa usando su encabezado de correlación. Chromium verifica filtros, paginación y acceso por permiso con API simulada.

La [prueba manual de consentimiento](../../docs/planning/v1/MANUAL_CONSENT_QA.md) usa un contacto de WhatsApp sintético y distingue una baja anterior de la autorización vigente. Chromium comprueba el reintento, la paginación y la visibilidad por permiso.

## Comandos válidos

```powershell
npm run build
docker compose --profile visual up --build --abort-on-container-exit
```

Los screenshots se revisan manualmente. `npm test` no es válido hasta configurar runner/target/specs.

## Cobertura prioritaria pendiente

- Token storage, guards y interceptor: headers, exclusiones, refresh concurrente y retry/fallo.
- TenantService y OperationalService: URLs, envelopes, paginación y multipart.
- Formularios de auth/onboarding/settings y permisos.
- Gating por plan y estados operational 401/402/403/404.
- Chats solo lectura, transformación del workflow y analytics.
- Rutas públicas, onboarding sin guard y wildcard.
- Responsive, claro/oscuro, teclado, lector y axe.
- Fallback, cache y headers de Nginx.
- Baselines con `toHaveScreenshot` si se desea regresión visual real.

## Estrategia recomendada

Elegir explícitamente un runner compatible con Angular 21, añadir target y specs antes de habilitar `npm test`. Para E2E, separar smoke público de flujos autenticados y usar un ambiente/mocks reproducibles; nunca usar credenciales o tokens reales en fixtures y capturas.
