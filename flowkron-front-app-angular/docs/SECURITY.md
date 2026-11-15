# Seguridad

## Frontera de confianza

El frontend nunca es autoridad de autenticación, tenant, roles, permisos ni plan. Guards, botones ocultos y signals mejoran UX; las dos APIs deben validar cada petición.

## Tokens y tenant

Access token, refresh token y tenant ID se guardan en `localStorage`. Esto permite restaurar sesión, pero expone los tokens ante XSS. Consecuencias:

- evitar `innerHTML`, bypasses de sanitización y scripts no confiables;
- aplicar CSP y reducir terceros;
- no registrar tokens, headers, query tokens ni datos personales;
- limpiar las tres claves en logout o fallo de sesión;
- considerar cookies HttpOnly/BFF si cambia el modelo de seguridad.

`X-Tenant-ID` es contexto solicitado, no prueba de pertenencia. El backend debe comprobar la membresía del JWT.



Las URLs de API controlan dónde el interceptor enviará bearer y tenant. El pipeline debe restringirlas a orígenes HTTPS confiables. Revisar cuidadosamente cualquier cambio de build args para evitar exfiltración de credenciales.

## Invitaciones y reset

Tokens llegan por query/formulario y deben tratarse como secretos de un solo uso. Evitar analytics, logs, referrers o screenshots que los capturen. El backend controla expiración, reutilización, rate limiting y revocación.

## Uploads y datos

Avatar/logo se envían multipart. El frontend solo restringe el selector a PNG/JPEG/WebP; backend y almacenamiento deben validar tipo real, tamaño, contenido y autorización. Perfil, miembros, conversaciones y leads contienen PII: aplicar minimización, retención y controles de acceso.

## Runtime y planes

Errores y gating del plan no sustituyen autorización. Nunca exponer ingest keys salvo en el flujo único definido por backend; actualmente no existe pantalla que llame provisión de runtime.

## Runtime web

- **Sanitización de HTML y XSS:** Angular sanitiza de forma nativa todo el contenido renderizado. Es fundamental no utilizar métodos de escape como `DomSanitizer.bypassSecurityTrust*` o asignaciones directas a `innerHTML` a través de `ElementRef` sin sanitización previa de confianza, para evitar Cross-Site Scripting (XSS).
- **Hardening en Producción (Nginx/Gateway):** Aunque el contenedor local de Nginx viene con configuración mínima, en producción se deben inyectar las cabeceras de seguridad requeridas en el proxy inverso o balanceador:
  - `Content-Security-Policy` (CSP) estricto para limitar los orígenes de scripts y conexiones.
  - `X-Frame-Options: DENY` o `SAMEORIGIN` para mitigar Clickjacking.
  - `X-Content-Type-Options: nosniff` para evitar sniffing de MIME types.
  - `Referrer-Policy: strict-origin-when-cross-origin`.
  - `Strict-Transport-Security` (HSTS) para obligar conexiones HTTPS seguras.
- **Auditoría de Dependencias:** Ejecutar periódicamente análisis de vulnerabilidades utilizando `npm audit` para mitigar riesgos derivados de librerías de terceros desactualizadas.

