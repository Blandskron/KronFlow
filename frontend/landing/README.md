# KronFlow Landing (`frontend/landing`)

Landing pública de **KronFlow — Intelligent CRM** (*Smart conversations. Seamless automation.* · Open Source · By **BLANDSKRON**) construida con **Angular 21.2** standalone en modo **Zoneless (`provideZonelessChangeDetection`) + `ChangeDetectionStrategy.OnPush`**, Floating Glassmorphism Teal/Esmeralda/Cyan, tipografía `Sora` + `Inter` + `JetBrains Mono`, Lighthouse Desktop `100/100/100/100` y cumplimiento WCAG 2.2 AA.

## Alcance funcional

- Rutas públicas `/` y `/politica-privacidad`, con redirección wildcard a `/`.
- Bento Grid de capacidades (`01`–`04`), vista previa conversacional RAG/HITL, sección de arquitectura Open Source y footer legal.
- Enlaces dinámicos hacia `${appUrl}/login` y `${appUrl}/registrarse`.
- Selector claro/oscuro persistido en `localStorage['theme']` con sincronización de `<meta name="theme-color">`.
- Modal nativo `<dialog>` accesible (`Escape` y gestión de foco) para términos de uso.
- Formulario de contacto reactivo accesible (`aria-invalid`, `aria-describedby`, `role="status"`/`role="alert"`) integrado a Django IAM mediante cookie/token CSRF (`POST /api/v1/contact/messages/` con `X-CSRFToken`).

## Desarrollo local

```sh
npm ci
npm start
```

Disponible en `http://localhost:4200`. Validación y build de producción:

```sh
npm run lint
npm test
npm run build
```

Salida de producción: `dist/landing/browser`.

## Docker

```sh
docker compose --env-file .env.local up --build
```

Nginx endurecido sirve la SPA en `http://localhost:8080` con fallback SPA, cabeceras de seguridad, `robots.txt`, `kronflow-og-card.svg` y healthcheck sobre `/`.

| Build arg | Default Docker | Uso |
| --- | --- | --- |
| `APP_PUBLIC_URL` | `http://localhost:8081` | Base URL para `/login` y `/registrarse` |
| `CONTACT_API_BASE_URL` | `http://localhost:8000` | Origen Django IAM para CSRF y contacto |
| `SALES_WHATSAPP_NUMBER` | `""` | Botón flotante de WhatsApp (oculto si está vacío) |

## Validación

- `npm run lint`: ESLint + `@angular-eslint/template/accessibility` (`0` errores, `0` warnings).
- `npm test`: Vitest en modo Zoneless (`11/11` pruebas cubriendo `LandingComponent`, `ContactService`, `LegalModalComponent` y `ThemeService`).
- `npm run build`: bundle de producción con `0` warnings y presupuestos CSS verificados.
- `docker compose --profile visual up --build --abort-on-container-exit`: smoke Playwright en `tests/visual/kronflow-landing.visual.spec.ts`.

## Documentación

Consulta [docs/README.md](docs/README.md) para arquitectura, configuración, seguridad y testing. Las reglas para agentes viven en [AGENTS.md](AGENTS.md).
