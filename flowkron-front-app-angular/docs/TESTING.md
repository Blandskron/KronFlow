# Testing

## Estado actual

No hay specs unitarios Angular, runner ni target `test` en `angular.json`. Aunque `package.json` contiene `"test":"ng test"`, el comando falla con `Cannot determine project or target for command`.

El único spec Playwright, `tests/visual/flowkron-front.visual.spec.ts`, valida:

- `/` redirige a `/login`;
- headings/texto de login;

No usa mocks, backends, login real, `toHaveScreenshot` ni baselines. Es smoke de render público con evidencia visual, no integración end-to-end ni regresión visual automatizada.

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
