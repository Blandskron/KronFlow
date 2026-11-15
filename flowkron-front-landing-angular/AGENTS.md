# AGENTS.md

Fuente unica de contexto e instrucciones agenticas para `flowkron-front-landing-angular`. Los adaptadores `CLAUDE.md` y `GEMINI.md` solo remiten aqui.

## Proposito y limites

SPA publica Angular 21 para marketing y conversion. No contiene autenticacion, backend propio de contacto, precios configurables ni persistencia de negocio. El unico cliente HTTP activo es el formulario de contacto contra Django IAM con CSRF.

No asumas capacidades inexistentes:

- `npm test` esta declarado en `package.json`, pero no hay target `test` en `angular.json`, runner unitario ni specs bajo `src/`.
- El unico spec Playwright es smoke funcional con screenshots; no usa `toHaveScreenshot` ni baselines.
- El formulario de contacto obtiene CSRF desde Django IAM, envia `POST /api/v1/contact/messages/` y resetea tras respuesta exitosa.
- El input de email del hero no esta conectado al CTA ni a un `FormControl`.
- Los textos de terminos/privacidad son placeholders y requieren revision legal antes de produccion.
- No existe `environment.prod.ts` ni file replacement de Angular; Docker modifica `environment.ts` en una capa de build.

## Mapa

| Ruta | Responsabilidad |
| --- | --- |
| `src/app/domains/landing/features/landing-page/landing-page.component.ts` | Pagina principal, contenido, formulario, WhatsApp y CTAs |
| `src/app/domains/landing/data-access/contact.service.ts` | CSRF y envio de contacto a Django IAM |
| `src/app/domains/legal/features/privacy-policy/` | Pagina publica de politica de privacidad |
| `src/app/core/services/theme.service.ts` | Tema y localStorage |
| `src/app/shared/ui/` | Toggle y modal legal |
| `src/app/app.routes.ts` | Ruta raiz, privacidad y wildcard |
| `src/environments/environment.ts` | Defaults compilados |
| `src/styles.css` | Tokens y estilos globales; importa Google Fonts |
| `tests/visual/` | Smoke Playwright externo al toolchain Angular |
| `Dockerfile` / `nginx.conf` | Build Node y runtime Nginx |

## Invariantes

- Mantener componentes standalone, TypeScript/templates estrictos y rutas lazy.
- CTAs de login/registro derivan de `environment.appUrl`; WhatsApp de `salesWhatsAppNumber`.
- No incluir secretos en `environment.ts`: todo valor frontend queda publico en el bundle.
- Preservar accesibilidad basica: roles semanticos, labels, teclado, foco y contraste.
- Mantener responsive en anchos moviles/escritorio y ambos temas.
- El formulario ya envia datos a Django IAM; cualquier cambio requiere conservar contrato, CSRF, estados loading/error/success, privacidad, consentimiento y pruebas.
- El modal legal actual no implementa focus trap, `role=dialog`, `aria-modal` ni cierre Escape; no afirmar accesibilidad completa.

## Configuracion y seguridad

`APP_PUBLIC_URL`, `CONTACT_API_BASE_URL` y `SALES_WHATSAPP_NUMBER` son build args publicos, no secretos. Validar su formato/origen en el pipeline: `href`, `HttpClient` y `window.open` confian en valores compilados. La landing carga Manrope desde Google Fonts, creando una dependencia externa y consideraciones de CSP/privacidad.

ThemeService accede a `localStorage` y `document`; la app es CSR. Si se agrega SSR, debe proteger acceso a browser globals.

## Autorizacion del agente

Permitido dentro del alcance: leer codigo/docs, editar componentes/estilos/documentacion, crear tests y ejecutar build/smoke local.

Requiere aprobacion: dependencias/lockfile, Angular/TypeScript config, Docker/Nginx/Compose, CI/CD, nuevas integraciones externas, analytics/cookies o cambio de contratos/URLs publicos.

No leer/modificar `.env`, `node_modules/`, `dist/`, `.angular/`, resultados generados ni workflows. No ejecutar limpieza destructiva de volumenes/caches salvo solicitud explicita.

## Validacion proporcional

```powershell
npm run build
```

- Docs: enlaces, referencias obsoletas, fences y `git diff --check`.
- UI/logica: build y smoke Playwright; revisar screenshots manualmente si cambio diseno.
- No ejecutar/reportar `npm test` como valido hasta configurar un target real.
- Docker visual instala Playwright en runtime y requiere red; `--abort-on-container-exit` evita dejar el stack abierto.
- Para cambios visuales, verificar al menos movil/escritorio, claro/oscuro y navegacion por teclado.

## Documentos canonicos

- [Indice](docs/README.md)
- [Arquitectura y comportamiento](docs/ARCHITECTURE.md)
- [Configuracion y despliegue](docs/CONFIGURATION.md)
- [Contenido, seguridad y accesibilidad](docs/SECURITY_AND_CONTENT.md)
- [Operacion](docs/OPERATIONS.md)
- [Testing](docs/TESTING.md)

## Definicion de terminado

El diff respeta alcance, no expone secretos, compila, conserva rutas/CTAs/tema, actualiza pruebas/documentacion y declara cualquier validacion no ejecutada.
