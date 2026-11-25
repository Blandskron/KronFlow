# Seguridad, contenido y accesibilidad

## Frontera de seguridad

Todo lo compilado en una SPA es publico. `APP_PUBLIC_URL`, `SALES_WHATSAPP_NUMBER` y `contactApiBaseUrl` son configuracion, nunca secretos. No agregar API keys, tokens ni credenciales a environments, templates o Docker args.

La landing no procesa autenticacion. El formulario de contacto llama al endpoint publico de Django IAM con CSRF; los CTAs transfieren al usuario a la app privada, donde se maneja auth y autorizacion.

## Redirecciones y terceros

- `appUrl` controla `href` de login/registro; restringir el build arg a `https` y dominio aprobado.
- WhatsApp usa `wa.me` y `noopener`; el numero debe contener solo digitos.
- Google Fonts (`Sora`, `Inter`, `JetBrains Mono`) recibe una solicitud del navegador. Evaluar self-host/CSP/consentimiento segun politica de privacidad.
- Nginx no agrega security headers especificos; deben configurarse en Nginx o borde antes de produccion.

## Formulario y privacidad

El formulario envia datos a Django IAM con este flujo:

- `GET /api/v1/contact/csrf/` obtiene `csrfToken` y cookie CSRF.
- `POST /api/v1/contact/messages/` envia `X-CSRFToken` y `withCredentials`.
- El cliente valida requeridos, largos, email, telefono, aceptacion legal y rechaza HTML, caracteres de control y secuencias SQL de alto riesgo.
- Angular no usa `innerHTML` para datos ingresados; la salida interpolada queda escapada por defecto.
- El backend repite las validaciones, aplica throttling y escribe con ORM.

Pendiente antes de publicar:

- definir finalidad, minimizacion, retencion y base legal;
- reemplazar textos legales provisionales;
- no incluir PII en analytics/logs sin politica explicita.

El checkbox habilita submit y registra `accept_terms=true`, pero no constituye por si mismo consentimiento legal suficiente sin textos legales finales.

## Contenido provisional

- Telefono, WhatsApp y metricas comerciales son valores estaticos/default.
- Logos `Clientes`/`Partners` son placeholders textuales.
- Terminos y privacidad declaran explicitamente que son textos base.
- Las metricas (`342`, `$45.2k`, etc.) no provienen de datos reales.

Validar contenido, claims comerciales, contacto, jurisdiccion, copyright y documentos legales antes de publicar.

## Accesibilidad observada

Positivo: HTML semantico basico, labels accesibles en icon buttons, botones reales, inputs con placeholders, foco visible y resultado de formulario anunciado con `role=status`/`role=alert`.

Brechas:

- Inputs no tienen `<label>` asociado; placeholders no lo sustituyen.
- Modal carece de `role=dialog`, `aria-modal`, titulo asociado, focus trap, restauracion de foco y cierre Escape.
- Menu movil desaparece sin navegacion alternativa.
- No hay skip link.
- El CTA del hero ignora su email.
- Tema inicial no respeta preferencia del sistema.

Estas brechas deben tratarse como deuda, no como capacidades implementadas.
