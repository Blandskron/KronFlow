# KronFlow Landing (`flowkron-front-landing-angular`)

Landing pública de **KronFlow — Intelligent CRM** (*Smart conversations. Seamless automation.* · Open Source · By **BLANDSKRON**) construida con Angular 21 standalone Zoneless (`OnPush`), Floating Glassmorphism Teal/Esmeralda/Cyan, enlaces hacia la aplicación privada, contacto por WhatsApp, tema claro/oscuro y formulario de contacto conectado a Django IAM.

## Alcance real

- Rutas publicas `/` y `/politica-privacidad`, con redireccion wildcard a `/`.
- CTAs hacia `${appUrl}/login` y `${appUrl}/register`.
- Botón WhatsApp con mensaje preconfigurado.
- Tema persistido en `localStorage['theme']`.
- Modales con textos legales provisionales.
- Formulario de contacto validado en cliente y enviado a Django IAM con CSRF.

El formulario obtiene CSRF desde `CONTACT_API_BASE_URL`, envia `POST /api/v1/contact/messages/` con `X-CSRFToken` y reinicia sus campos tras una respuesta exitosa. El email del hero no esta enlazado al registro.

## Desarrollo

```powershell
npm ci
npm start
```

Disponible en `http://localhost:4200`. Build de producción:

```powershell
npm run build
```

Salida: `dist/flowkron-front-landing-angular/browser`.

## Docker

```powershell
docker compose --env-file .env.local up --build
```

Nginx publica la SPA en `http://localhost:8080` con fallback a `index.html`, cache inmutable para assets hasheados y healthcheck sobre `/`.

## Configuración de build

| Build arg | Default | Uso |
| --- | --- | --- |
| `APP_PUBLIC_URL` | `http://localhost:8081` | Base para `/login` y `/register` |
| `CONTACT_API_BASE_URL` | `http://localhost:8000` | Origen Django IAM para CSRF y contacto |
| `SALES_WHATSAPP_NUMBER` | `521234567890` | Número sin `+`, espacios ni separadores para `wa.me` |

Docker reemplaza estos literales en `src/environments/environment.ts` durante la etapa de build. No son variables runtime: cambiar el ambiente exige reconstruir la imagen.

## Validación

```powershell
npm run build
docker compose --profile visual up --build --abort-on-container-exit
```

El repositorio contiene un smoke Playwright que verifica render, CTAs y tema, y guarda dos screenshots. No compara contra baselines, por lo que no es una suite de regresión visual. `npm test` no funciona actualmente porque `angular.json` no define target `test` y no existen specs unitarios.

## Documentación

Consulta [docs/README.md](docs/README.md). Las instrucciones para agentes están consolidadas en [AGENTS.md](AGENTS.md).
