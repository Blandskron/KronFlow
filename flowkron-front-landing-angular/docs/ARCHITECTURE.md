# Arquitectura y comportamiento

## Aplicación

SPA Angular 21 con standalone components, bootstrap mediante `bootstrapApplication`, routing lazy y `HttpClient` para el formulario de contacto. No usa NgModules, SSR, hydration, state manager ni backend propio.

```text
index.html -> main.ts -> AppComponent -> RouterOutlet
                                  -> / lazy LandingComponent
                                  -> /politica-privacidad lazy PrivacyPolicyComponent
                                  -> ** redirect /
```

`AppComponent` inicializa `ThemeService`; la landing completa vive en `LandingComponent` y la politica de privacidad en `PrivacyPolicyComponent`. Los componentes compartidos son el toggle de tema y modal legal.

## Secciones

- Header sticky con anchors y CTAs.
- Hero comercial con input email no conectado.
- Logos/placeholders de confianza.
- Problema/solución, agentes, métricas y casos de uso estáticos.
- Contacto con datos estáticos y formulario conectado a Django IAM.
- CTA final, footer y modales legales.
- Botón flotante WhatsApp.

No hay una sección de pricing aunque documentación anterior hablaba de planes/precios.

## Navegación externa

Enlaces compilados:

- login: `${environment.appUrl}/login`
- registro/CTAs: `${environment.appUrl}/register`
- WhatsApp: `https://wa.me/${salesWhatsAppNumber}?text=<mensaje>` mediante `window.open(..., 'noopener')`

No hay router guards ni open redirect basado en query string; aun así, el pipeline controla `APP_PUBLIC_URL` y debe restringirlo a un origen confiable.

## Estado local

`ThemeService` mantiene un signal `isDark`, agrega/remueve clase `dark` en `<html>` y persiste `localStorage['theme']` como `light|dark`. Si no existe preferencia, inicializa light y la escribe. No consulta `prefers-color-scheme`.

El estado del formulario y de modales vive en `LandingComponent`; se pierde al recargar.

## Formulario

Reactive Form exige nombre, email válido, mensaje y aceptación. Antes de enviar, obtiene `csrfToken` desde `${environment.contactApiBaseUrl}/api/v1/contact/csrf/` con cookies habilitadas y luego publica en `/api/v1/contact/messages/` con header `X-CSRFToken`.

La validación cliente limita largos, formato telefónico, HTML, caracteres de control y secuencias SQL de alto riesgo. El backend Django repite esas validaciones y persiste con ORM.

## Estilos y assets

CSS global define tokens de ambos temas, layout y responsive; CSS extenso del componente define la landing. Lucide Angular renderiza iconos SVG. No se configuran assets locales. Manrope se carga desde Google Fonts con `@import`, por lo que el render depende de un tercero.
