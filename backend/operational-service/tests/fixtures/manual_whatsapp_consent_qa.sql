-- Run only in a disposable QA workspace with WhatsApp disconnected.
\if :{?operational_schema}
\else
\set operational_schema operational
\endif

WITH active_company AS (
    SELECT auth_tenant_id, schema_name
    FROM :"operational_schema".tenant_runtime
    WHERE schema_name = :'tenant_schema' AND status = 'active'
), contact AS (
    INSERT INTO :"tenant_schema".clientes (
        rut, nombre, whatsapp_id, consentimiento_datos, fecha_consentimiento, canal_consentimiento, version_politica
    )
    SELECT 'qa:whatsapp-consent', 'Contacto QA WhatsApp', 'qa-consent-v8',
           TRUE, '2026-01-01T12:00:00Z', 'whatsapp', 'v1.0'
    FROM active_company
    ON CONFLICT (rut) DO NOTHING
    RETURNING id
), current_decision AS (
    INSERT INTO :"tenant_schema".whatsapp_consent_state (client_id, decision_at, authorized_from)
    SELECT id, '2026-01-01T12:14:00Z', '2026-01-01T12:14:00Z' FROM contact
    RETURNING client_id
), evidence AS (
    SELECT minute, 'whatsapp.consent.changed' AS event_type,
           jsonb_build_object(
               'accepted', TRUE, 'source', 'whatsapp_message', 'policy_version', 'v1.0',
               'decision_at', '2026-01-01T12:00:00Z'::timestamptz + make_interval(mins => minute)
           ) AS payload
    FROM generate_series(0, 14) AS minute
    UNION ALL
    SELECT 15, 'whatsapp.consent.prior_withdrawal',
           jsonb_build_object('decision_at', '2026-01-01T12:13:30Z')
)
INSERT INTO :"operational_schema".system_events (auth_tenant_id, schema_name, event_type, payload, created_at)
SELECT auth_tenant_id, schema_name, event_type, payload || jsonb_build_object('client_id', client_id),
       '2026-01-01T12:15:00Z'::timestamptz + make_interval(mins => minute)
FROM active_company CROSS JOIN current_decision CROSS JOIN evidence
ORDER BY minute;
