# Operación y despliegue

## Desarrollo

```powershell
npm ci
npm start
```

Servidor Angular en `http://localhost:4200`. Build reproducible:

```powershell
npm run build
```

## Docker

```powershell
$env:APP_PUBLIC_URL='https://app.example.com'
$env:CONTACT_API_BASE_URL='https://api.example.com'
$env:SALES_WHATSAPP_NUMBER='521234567890'
docker compose --env-file .env.local up --build
```

Verifica en `http://localhost:8080` los href de login/registro y WhatsApp. Los args se hornean en el bundle: cambiar variables sin rebuild no tiene efecto.

## Smoke Playwright

```powershell
docker compose --profile visual up --build --abort-on-container-exit
```

El contenedor instala Playwright durante cada ejecución, prueba render/CTAs/dark mode y escribe `visual-test-results/landing.png` y `landing-dark.png`. Revisa las imágenes manualmente; no hay baseline ni comparación pixel a pixel.

## Diagnóstico

### CTA apunta al ambiente equivocado

1. Confirmar build arg efectivo.
2. Reconstruir sin reutilizar una imagen antigua si corresponde.
3. Inspeccionar href desde el navegador/smoke.
4. Verificar que el reemplazo literal del Dockerfile todavía coincide con `environment.ts`.

### Deep link devuelve 404

Confirmar que runtime use `nginx.conf` con fallback. Angular dev server ya maneja la SPA. El wildcard de Angular redirige rutas desconocidas a `/` después de cargar la app.

### Fuente no aparece

Revisar conectividad/CSP hacia Google Fonts. La app cae a Inter/system fonts si la importación falla.

### Formulario no genera contacto

Revisar consola/red del navegador, `CONTACT_API_BASE_URL`, CORS/CSRF del IAM y respuesta de `GET /api/v1/contact/csrf/`. El flujo esperado es obtener cookie/token CSRF y luego enviar `POST /api/v1/contact/messages/`.

## Checklist de publicación

- [ ] Build aprobado dentro de budgets.
- [ ] CTAs y WhatsApp apuntan al ambiente/número correctos.
- [ ] Contenido, métricas, partners y datos de contacto aprobados.
- [ ] Términos/privacidad reemplazados por versiones legales.
- [ ] Accesibilidad crítica corregida/probada con teclado y lector.
- [ ] Security headers, HTTPS y caching validados en borde.
- [ ] Política para Google Fonts/terceros aprobada.
- [ ] Responsive y temas verificados en navegadores objetivo.
- [ ] Smoke Playwright aprobado y screenshots revisados.
- [ ] Formulario de contacto, privacidad, CORS y CSRF probados contra el IAM objetivo.

## Diagnostico adicional

### CSRF cookie not set en formulario

Confirmar que `CONTACT_API_BASE_URL` apunte al origen publico de Django IAM y que la imagen se haya reconstruido. En el backend, el origen publico de la landing debe estar en `CORS_ALLOWED_ORIGINS`/`CSRF_TRUSTED_ORIGINS`; si el navegador no conserva la cookie `csrftoken` entre `GET /api/v1/contact/csrf/` y `POST /api/v1/contact/messages/`, Django respondera `CSRF cookie not set`.
