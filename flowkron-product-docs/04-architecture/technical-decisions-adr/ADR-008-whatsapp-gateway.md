# ADR-008 — Gateway WhatsApp

Estado: Propuesto (`PROPOSED`)

## Contexto

Operational recibe eventos normalizados por endpoints ingest, pero el stack no contiene el gateway que autentica proveedor, valida webhooks y transforma/reintenta eventos.

## Decisión pendiente

Seleccionar proveedor y límite del gateway; definir firma webhook, idempotencia, colas/retries, orden, dead-letter, rate limits, secrets, media, estados de entrega y observabilidad.

No debe confundirse el CTA `wa.me` ni la API ingest con una integración WhatsApp completa.
