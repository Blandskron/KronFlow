# Testing

## Estado actual

No hay pruebas unitarias Angular. Aunque `package.json` define `"test":"ng test"`, `angular.json` no tiene target `test` y `npm test` falla con `Cannot determine project or target for command`.

Existe un único spec Playwright en `tests/visual/flowkron-landing.visual.spec.ts`. Verifica:

- heading principal visible;
- href de login y registro;
- toggle agrega clase `dark`;
- captura screenshots claro/oscuro.

No usa `expect(page).toHaveScreenshot()`, no hay baselines y no compara píxeles. Es smoke funcional con evidencia visual, no regresión visual automatizada.

## Comandos válidos

```powershell
npm run build
docker compose --profile visual up --build --abort-on-container-exit
```

`npm test` no es válido hasta configurar builder/runner y specs.

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

## Recomendación

Elegir explícitamente un runner compatible con Angular 21 antes de habilitar `npm test`. Para visual regression, fijar Playwright como dependencia/versionada, configurar proyecto y baselines, y usar `toHaveScreenshot`; revisar actualizaciones de snapshots en code review.
