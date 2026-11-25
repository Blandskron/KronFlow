# Testing

## Estado actual

- **Pruebas unitarias (Angular 21 + Vitest):** Configuradas mediante `@angular/build:unit-test` (`runner: "vitest"` y `tsconfig.spec.json`). Cobertura base activa en `ThemeService`, `ContactService`, `LegalModalComponent` y `LandingComponent`.
- **Linting:** Configurado con `eslint` + `angular-eslint` (TypeScript + templates + accesibilidad) vía `npm run lint`.

Existe un spec Playwright en `tests/visual/kronflow-landing.visual.spec.ts`. Verifica:

- heading principal visible;
- href de login y registro;
- toggle agrega clase `dark`;
- captura screenshots claro/oscuro.

No usa `expect(page).toHaveScreenshot()`, no hay baselines y no compara píxeles. Es smoke funcional con evidencia visual, no regresión visual automatizada.

## Comandos válidos

```powershell
npm run build
npm test
npm run lint
docker compose --profile visual up --build --abort-on-container-exit
```

`npm test` ejecuta Vitest en modo CI (`--watch=false`); usa `npm run test:watch` para desarrollo interactivo.

## Cobertura pendiente

- Rutas raíz y wildcard.
- ThemeService: valor guardado, toggle y fallback.
- Validadores/reset del formulario, estados loading/success/error y contrato CSRF/contacto.
- URLs seguras y normalización de WhatsApp.
- Modales legales y accesibilidad de foco/teclado.
- Anchors y navegación móvil.
- Responsive en viewport móvil y escritorio.
- Error si build args no se reemplazan.
- Headers/caching/fallback de Nginx.
- Baselines reales si se desea regresión visual.

## Estándares de prueba

La suite unitaria corre con Vitest en modo Zoneless (`npm test`). Al agregar pruebas de regresión visual automatizada con Playwright `toHaveScreenshot()`, fijar versión y revisar snapshots en code review.
