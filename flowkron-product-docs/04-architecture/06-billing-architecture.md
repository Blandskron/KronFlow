# Arquitectura de planes y suscripción

Versión: 1.0
Tipo: Current State + Target Architecture
Estado: `PARTIAL`

## Implementado

- Planes Auth: `free`, `starter`, `pro`, `enterprise`.
- Estados: `free`, `trialing`, `active`, `past_due`, `canceled`, `unpaid`.
- Entitlements por plan intersectados con RBAC.
- `requires_paid_plan` para gating frontend.
- Activación administrativa de suscripción.
- Provisioning operacional síncrono al activar.
- Runtime operational bloquea plan Free con HTTP 402.
- Pricing UI estático con contacto por WhatsApp.

## Limitaciones

- La pantalla de pricing no llama activación ni checkout.
- Una activación puede persistir suscripción y luego fallar provisioning; ambos estados deben reconciliarse.
- `billing_reference` operacional no participa en routers actuales.

## No implementado

- Payment provider/checkout.
- Pagos, facturas y conciliación.
- Webhooks y renovaciones automáticas.
- Cobro recurrente, reintentos y cancelación automatizada.
- Portal de billing autoservicio.

Estas capacidades permanecen arquitectura objetivo y requieren ADR/contrato antes de implementación.
