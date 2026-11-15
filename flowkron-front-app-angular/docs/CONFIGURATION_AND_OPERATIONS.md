# Configuración y operación

## Variables locales


Estas variables se compilan dentro del bundle Angular durante el build; cambiar `.env.local` requiere reconstruir la imagen o volver a ejecutar `npm run build` con la configuracion equivalente.

## Angular

- Angular 21, TypeScript 5.9, ES2022 y templates estrictos.
- Build default `production`; serve default `development`.
- Output `dist/flowkron-front-app-angular/browser`.
- Budgets: initial 600 kB/1 MB; component style 8 kB/12 kB.
- No hay target `test` en `angular.json`.
- No existe `environment.prod.ts` ni `fileReplacements`.

`environment.ts` conserva `production:false` incluso en build productivo; el flag no se usa actualmente.

## Configuración compilada

| Campo | Default del repositorio |
| --- | --- |
| `apiUrl` | `http://localhost:8000/api/v1` |
| `operationalApiUrl` | `http://localhost:8001/api/v1` |
| `agentCoreApiUrl` | `http://localhost:8002/api/v1` |
| `landingUrl` | `http://localhost:8080` |
| `salesWhatsAppNumber` | `521234567890` |

El Dockerfile reemplaza literalmente estos campos antes del build. Un refactor del formato de `environment.ts` puede hacer que un reemplazo no coincida y deje el default, por lo que deben verificarse las URLs finales en navegador/smoke.

### Dockerfile y Compose


- `docker-compose.yml` carga `.env.local` si existe y pasa build args al Dockerfile; sin `.env.local`, Compose usa defaults locales (`localhost:8000/8001/8002`, landing `8080` y app `8081`);
- en un `docker build` directo, sin `--build-arg`, aplican los defaults productivos declarados en el Dockerfile;
- para cambiar URLs hay que reconstruir la imagen con `.env.local`, variables de entorno de Compose o `docker build --build-arg ...`; cambiar variables despues del build no modifica el JavaScript ya generado.

Todos los valores terminan públicos en JavaScript. No usar build args para secretos.

## Desarrollo y build

```powershell
npm ci
npm start
npm run build
```

## Docker/Nginx

```powershell
docker compose --env-file .env.local up --build
```

Node 20 Alpine compila y Nginx 1.27 Alpine sirve en `http://localhost:8081`. Nginx configura fallback SPA, gzip y cache inmutable de un año para assets. No agrega CSP, HSTS, frame, referrer ni permissions policy.

## Smoke

```powershell
docker compose --profile visual up --build --abort-on-container-exit
```


## Diagnóstico

- API/CORS: confirmar las URLs efectivamente compiladas; cambiar variables después del build no tiene efecto.
- Dashboard vuelve a login: revisar tokens, `/auth/me/`, refresh y CORS; no desactivar guards.
- Operational 402/403/404: puede significar plan requerido, runtime suspendido/no autorizado o no provisionado, respectivamente.
- Deep link 404: verificar que se use el `nginx.conf` con fallback.

## Checklist de release

- [ ] Build dentro de budgets.
- [ ] Login, refresh, logout, verificación, reset e invitación probados.
- [ ] Tenant, permisos, carga de archivos y gating de plan probados.
- [ ] Estados 401/402/403/404 operacional verificados.
- [ ] Responsive, temas, teclado y contenido revisados.
- [ ] Security headers/HTTPS/CSP/terceros aprobados en el borde.
