# Testing

## Estado actual

- **Pruebas unitarias (Angular 21 + Vitest):** Configuradas mediante `@angular/build:unit-test` (`runner: "vitest"` y `tsconfig.spec.json`). Cobertura base activa en `src/app/core/` (`token-storage`, `theme.service`, `auth.interceptor`, `auth.guard`, `no-auth.guard`).
- **Linting:** Configurado con `eslint` + `angular-eslint` (TypeScript + templates + accesibilidad) vía `npm run lint`.

El spec Playwright, `tests/visual/flowkron-front.visual.spec.ts`, valida:

- `/` redirige a `/login`;
- headings/texto de login;

Los casos de WhatsApp, Bandeja, Contactos y Seguimiento de leads sustituyen las APIs por respuestas sintéticas. Se comprueban búsqueda, paginación, navegación y marcas de lectura. El CRM cubre reintentos de ficha y actividad, conflictos de nombre y etapa, distinción entre acceso denegado y un fallo recuperable, restauración de filtros con el historial y salida de una página vacía tras guardar. El login público conserva su captura de render. Los casos usan stubs de proveedores y credenciales sintéticas.

El caso de Analytics usa un viewport móvil y verifica el corte parcial, los días con ceros, la distribución sin denominador, el cambio de zona y la recuperación con teclado después de un filtro inválido. El resumen sigue disponible si falla el reporte diario.

En Chromium se comprueban con API simulada el alta desde el contacto, la recarga tras un conflicto, el historial, el retorno al listado con filtro y la vista de solo lectura.

El caso de alta de contactos comprueba validación del teléfono, repetición de la misma solicitud tras una confirmación incierta, recuperación de datos concurrentes y enlace al seguimiento.

Las vistas de Notificaciones (Pendientes e Historial), Privacidad (lectura, revisión y cierre), Auditoría (correlación, filtros y paginación) y Consentimiento (baja anterior vs. autorización vigente) se cubren con casos de Chromium usando API simulada y pruebas de integración PostgreSQL en Operational.

## Comandos válidos

```powershell
npm run build
npm test
npm run lint
docker compose --profile visual up --build --abort-on-container-exit
```

Los screenshots visuales de Playwright se revisan manualmente. `npm test` ejecuta Vitest en modo CI (`--watch=false`); usa `npm run test:watch` para desarrollo interactivo.

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
