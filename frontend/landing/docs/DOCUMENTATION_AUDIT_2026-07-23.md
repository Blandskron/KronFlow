# Auditoría documental — 2026-07-23

Se contrastaron la landing Angular, su servicio de contacto, environment, Docker/Nginx y smoke disponible.

## Hechos confirmados

- El formulario obtiene CSRF de Auth y envía `POST /api/v1/contact/messages/`.
- Los CTAs de app y WhatsApp usan valores públicos compilados en `environment.ts`.
- El email del hero no está conectado al CTA ni a un `FormControl`.
- Los textos de términos y privacidad son placeholders que requieren revisión legal.
- No existe target de tests unitarios Angular; el smoke Playwright no posee baselines de regresión.

No se inspeccionaron `.env` ni se considera que la landing tenga backend propio.
