-- Use only in a disposable QA workspace after initiating the lead in manual_lead_qa.sql.
-- Pass tenant_schema and operational_schema explicitly to psql.
SELECT auth_tenant_id AS qa_tenant_id
FROM :"operational_schema".tenant_runtime
WHERE schema_name = :'tenant_schema' AND status = 'active'
\gset

SELECT lead.id AS qa_lead_id
FROM :"tenant_schema".leads AS lead
JOIN :"tenant_schema".clientes AS contact ON contact.id = lead.cliente_id
WHERE contact.rut = 'qa:lead-workflow'
ORDER BY lead.id
LIMIT 1
\gset

INSERT INTO :"operational_schema".system_events (auth_tenant_id, schema_name, event_type, payload)
SELECT :qa_tenant_id, :'tenant_schema', 'ingest.handoff.created', sample.payload
FROM (VALUES
    (jsonb_build_object('qa_fixture', 'handoff-with-lead', 'lead_id', CAST(:qa_lead_id AS bigint))),
    (jsonb_build_object('qa_fixture', 'handoff-without-target'))
) AS sample(payload)
WHERE NOT EXISTS (
    SELECT 1 FROM :"operational_schema".system_events AS event
    WHERE event.auth_tenant_id = :qa_tenant_id AND event.schema_name = :'tenant_schema'
      AND event.event_type = 'ingest.handoff.created'
      AND event.payload->>'qa_fixture' = sample.payload->>'qa_fixture'
);
