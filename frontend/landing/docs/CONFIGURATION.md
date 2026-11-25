# Configuración, build y runtime

## Variables locales

La landing usa `flowkron-front-landing-angular/.env.local` para build args de Docker Compose local. `.env.example` documenta `APP_PUBLIC_URL`, `CONTACT_API_BASE_URL`, `SALES_WHATSAPP_NUMBER` y `LANDING_PORT`.

Estas variables se compilan dentro del bundle Angular durante el build; cambiar `.env.local` requiere reconstruir la imagen o recompilar la app.

## Angular

- Angular 21, TypeScript 5.9, target ES2022 y templates estrictos.
- Build default `production`; serve default `development`.
- Output `dist/flowkron-front-landing-angular/browser`.
- Budgets: initial warning 600 kB/error 1 MB; component style warning 8 kB/error 12 kB.
- Paths: `@core/*`, `@shared/*`, `@features/*`.
- No hay target `test` en `angular.json`.

## Environment compilado

`src/environments/environment.ts` contiene:

```ts
production: false
appUrl: 'http://localhost:8081'
salesWhatsAppNumber: '521234567890'
contactApiBaseUrl: 'http://127.0.0.1:8000'
```

Incluso el build de producción conserva `production:false`; el código no utiliza actualmente ese flag. No existe `environment.prod.ts` ni `fileReplacements`.

## Build args Docker

| Argumento | Uso |
| --- | --- |
| `APP_PUBLIC_URL` | Reemplaza literalmente `appUrl` antes de `npm run build` |
| `CONTACT_API_BASE_URL` | Reemplaza `contactApiBaseUrl` antes de `npm run build` |
| `SALES_WHATSAPP_NUMBER` | Reemplaza `salesWhatsAppNumber` |

Son valores públicos del bundle. El reemplazo depende de que el archivo conserve el patrón `appUrl: '...'`/`salesWhatsAppNumber: '...'`; un refactor puede hacer que falle silenciosamente y deje defaults. Conviene validar el bundle/CTAs en smoke.

`contactApiBaseUrl` tambien es publico y debe apuntar al origen Django que expone `/api/v1/contact/csrf/` y `/api/v1/contact/messages/`. Ese origen debe estar en `CORS_ALLOWED_ORIGINS`/`CSRF_TRUSTED_ORIGINS` del backend para que CSRF con credenciales funcione.

## Docker y Nginx

Build: `node:20-alpine`, `npm ci`, Angular production. Runtime: `nginx:1.27-alpine`.

Nginx:

- fallback SPA con `try_files ... /index.html`;
- gzip para texto/CSS/JS/JSON/SVG;
- cache de un año e `immutable` para assets con extensiones conocidas;
- no define headers CSP, HSTS, frame, referrer ni permissions policy;
- healthcheck con wget a `/`.

Compose publica `8080:80`. El perfil `visual` instala `@playwright/test@1.53.0` en cada ejecución y requiere red; monta resultados en `./visual-test-results`.
