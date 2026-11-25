-- Use only in a disposable QA workspace. Pass tenant_schema explicitly to psql.
INSERT INTO :"tenant_schema".clientes (rut, nombre, email, canal_origen, consentimiento_datos)
VALUES ('qa:lead-workflow', 'Contacto QA sin lead', 'contacto-qa@example.test', 'qa_manual', FALSE)
ON CONFLICT (rut) DO NOTHING;
