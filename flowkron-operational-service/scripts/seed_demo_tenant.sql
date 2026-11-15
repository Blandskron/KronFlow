-- Demo seed for a provisioned tenant schema.
-- Usage:
--   Replace tenant_flowkron_demo with the target tenant schema and run it with psql/pgAdmin.
--
-- This seed is intentionally not executed automatically by the service.
-- The target schema must already have the current operational tables.

SET search_path TO tenant_flowkron_demo;

INSERT INTO ejecutivos (id, nombre, whatsapp, activo, leads_asignados, ultimo_asignado_at)
VALUES
    (1, 'Camila Torres', '00000000001', TRUE, 2, NOW() - INTERVAL '2 hours'),
    (2, 'Diego Ramirez', '00000000002', TRUE, 1, NOW() - INTERVAL '1 day'),
    (3, 'Valentina Soto', '00000000003', TRUE, 1, NOW() - INTERVAL '3 days')
ON CONFLICT (id) DO UPDATE SET
    nombre = EXCLUDED.nombre,
    whatsapp = EXCLUDED.whatsapp,
    activo = EXCLUDED.activo,
    leads_asignados = EXCLUDED.leads_asignados,
    ultimo_asignado_at = EXCLUDED.ultimo_asignado_at;

INSERT INTO clientes (
    rut, nombre, email, telefono, whatsapp_id, tipo_cliente, canal_origen,
    consentimiento_datos, fecha_consentimiento, canal_consentimiento, version_politica
)
VALUES
    ('DEMO-001', 'Sofia Herrera', 'sofia.herrera@example.com', '+00000000004', '00000000004', 'prospecto', 'whatsapp_directo', TRUE, NOW() - INTERVAL '6 days', 'whatsapp', 'v1.0'),
    ('DEMO-002', 'Martin Castillo', 'martin.castillo@example.com', '+00000000006', '00000000006', 'activo', 'instagram_ads', TRUE, NOW() - INTERVAL '14 days', 'whatsapp', 'v1.0'),
    ('DEMO-003', 'Fernanda Rojas', 'fernanda.rojas@example.com', '+00000000008', '00000000008', 'prospecto', 'facebook_ads', FALSE, NULL, NULL, 'v1.0'),
    ('DEMO-004', 'Javier Morales', 'javier.morales@example.com', '+00000000010', '00000000010', 'recurrente', 'referido', TRUE, NOW() - INTERVAL '30 days', 'whatsapp', 'v1.0'),
    ('DEMO-005', 'Paula Araya', 'paula.araya@example.com', '+00000000012', '00000000012', 'prospecto', 'tiktok_ads', TRUE, NOW() - INTERVAL '1 day', 'whatsapp', 'v1.0')
ON CONFLICT (rut) DO UPDATE SET
    nombre = EXCLUDED.nombre,
    email = EXCLUDED.email,
    telefono = EXCLUDED.telefono,
    whatsapp_id = EXCLUDED.whatsapp_id,
    tipo_cliente = EXCLUDED.tipo_cliente,
    canal_origen = EXCLUDED.canal_origen,
    consentimiento_datos = EXCLUDED.consentimiento_datos,
    fecha_consentimiento = EXCLUDED.fecha_consentimiento,
    canal_consentimiento = EXCLUDED.canal_consentimiento,
    version_politica = EXCLUDED.version_politica;

INSERT INTO leads (
    cliente_id, score_lead, clasificacion, plazo_compra, requiere_credito, estado,
    resumen_ia, followup_count, ultimo_followup_at, estado_seguimiento, ejecutivo_id
)
SELECT c.id, v.score_lead, v.clasificacion, v.plazo_compra, v.requiere_credito, v.estado,
       v.resumen_ia, v.followup_count, v.ultimo_followup_at, v.estado_seguimiento, v.ejecutivo_id
FROM (
    VALUES
        ('DEMO-001', 96, 'caliente', 'esta_semana', TRUE, 'en_proceso', 'Busca SUV hibrido con entrega rapida y financiamiento.', 2, NOW() - INTERVAL '3 hours', 'pendiente', 1),
        ('DEMO-002', 74, 'tibio', 'este_mes', FALSE, 'contactado', 'Interesado en sedan nuevo, compara Toyota Corolla y alternativas.', 1, NOW() - INTERVAL '1 day', 'pendiente', 2),
        ('DEMO-003', 38, 'frio', 'explorando', TRUE, 'nuevo', 'Pregunta por precios generales y opciones usadas.', 0, NULL, 'pendiente', NULL),
        ('DEMO-004', 88, 'caliente', 'este_dia', FALSE, 'ganado', 'Cliente recurrente listo para cerrar pickup diesel.', 3, NOW() - INTERVAL '2 days', 'cerrado', 3),
        ('DEMO-005', 55, 'tibio', 'cotizando', TRUE, 'contactado', 'Quiere SUV compacto y evaluacion de credito.', 1, NOW() - INTERVAL '5 hours', 'requiere_humano', 1)
) AS v(rut, score_lead, clasificacion, plazo_compra, requiere_credito, estado, resumen_ia, followup_count, ultimo_followup_at, estado_seguimiento, ejecutivo_id)
JOIN clientes c ON c.rut = v.rut
WHERE NOT EXISTS (
    SELECT 1
    FROM leads l
    WHERE l.cliente_id = c.id
);

INSERT INTO inventario_vehiculos (
    marca, modelo, anio, version, color, condicion, kilometraje,
    tipo_vehiculo, transmision, combustible, precio_lista, disponible
)
VALUES
    ('Toyota', 'RAV4', 2024, '2.5 AWD Sport', 'Blanco Perla', 'nuevo', 0, 'suv', 'automatica', 'hibrido', 32500000, TRUE),
    ('Toyota', 'Corolla', 2024, '2.0 CVT GR Sport', 'Negro Mica', 'nuevo', 0, 'sedan', 'cvt', 'bencina', 18900000, TRUE),
    ('Chevrolet', 'Tracker', 2024, '1.2T Premier', 'Rojo Fuego', 'nuevo', 0, 'suv', 'automatica', 'bencina', 17200000, TRUE),
    ('Mazda', 'CX-5', 2023, '2.5 Grand Touring', 'Azul Zafiro', 'usado', 18000, 'suv', 'automatica', 'bencina', 19800000, TRUE),
    ('Hyundai', 'Tucson', 2024, '1.6T Premium', 'Gris Titanio', 'nuevo', 0, 'suv', 'automatica', 'bencina', 22400000, TRUE),
    ('Kia', 'Sportage', 2024, '1.6T GT Line', 'Blanco Glaciar', 'nuevo', 0, 'suv', 'automatica', 'bencina', 21500000, TRUE),
    ('Suzuki', 'Vitara', 2023, '1.4T All Grip', 'Verde Jungle', 'usado', 12000, 'suv', 'automatica', 'bencina', 15600000, TRUE),
    ('Ford', 'Ranger', 2024, '3.2 TDCi 4x4 XLT', 'Plata Mercury', 'nuevo', 0, 'pickup', 'automatica', 'diesel', 28900000, TRUE),
    ('Nissan', 'Kicks', 2024, '1.6 Exclusive CVT', 'Naranja Sunset', 'nuevo', 0, 'suv', 'cvt', 'bencina', 16800000, TRUE),
    ('Honda', 'HR-V', 2023, '1.5T Sport', 'Negro Cristal', 'usado', 22000, 'suv', 'cvt', 'bencina', 16200000, FALSE)
ON CONFLICT DO NOTHING;

INSERT INTO conversaciones (session_id, message, creado_en)
VALUES
    ('00000000004', '{"source":"whatsapp","topic":"cotizacion_rav4","status":"active"}'::jsonb, NOW() - INTERVAL '6 hours'),
    ('00000000006', '{"source":"whatsapp","topic":"corolla","status":"active"}'::jsonb, NOW() - INTERVAL '1 day'),
    ('00000000012', '{"source":"whatsapp","topic":"credito_suv","status":"requires_human"}'::jsonb, NOW() - INTERVAL '5 hours')
ON CONFLICT DO NOTHING;

INSERT INTO mensajes_dashboard (whatsapp_id, rol, mensaje, creado_en)
VALUES
    ('00000000004', 'usuario', 'Hola, quiero cotizar una RAV4 hibrida con financiamiento.', NOW() - INTERVAL '6 hours'),
    ('00000000004', 'agente', 'Claro, tenemos una RAV4 2024 disponible. Te puedo simular cuotas.', NOW() - INTERVAL '5 hours 58 minutes'),
    ('00000000004', 'usuario', 'Perfecto, necesito entrega esta semana.', NOW() - INTERVAL '5 hours 40 minutes'),
    ('00000000006', 'usuario', 'Estoy comparando el Corolla 2024. Que versiones tienen?', NOW() - INTERVAL '1 day'),
    ('00000000006', 'agente', 'Tenemos Corolla 2.0 CVT GR Sport disponible en negro mica.', NOW() - INTERVAL '23 hours'),
    ('00000000012', 'usuario', 'Quiero una SUV compacta y necesito evaluar credito.', NOW() - INTERVAL '5 hours'),
    ('00000000012', 'agente', 'Te puedo derivar con un ejecutivo para revisar preaprobacion.', NOW() - INTERVAL '4 hours 55 minutes');

INSERT INTO mensajes_procesados (message_id)
VALUES
    ('demo-msg-001'),
    ('demo-msg-002'),
    ('demo-msg-003')
ON CONFLICT (message_id) DO NOTHING;

INSERT INTO solicitudes_derechos (whatsapp_id, tipo_derecho, estado, fecha_solicitud, fecha_limite, notas)
VALUES
    ('00000000008', 'acceso', 'pendiente', NOW() - INTERVAL '2 days', NOW() + INTERVAL '28 days', 'Cliente solicita copia de datos almacenados.'),
    ('00000000010', 'rectificacion', 'en_proceso', NOW() - INTERVAL '5 days', NOW() + INTERVAL '25 days', 'Actualizar correo de contacto.')
ON CONFLICT DO NOTHING;

INSERT INTO log_limpiezas (
    mensajes_eliminados, clientes_anonimizados, solicitudes_eliminadas, estado, detalle, notas
)
VALUES
    (12, 0, 1, 'exitoso', '{"job":"retention_cleanup","retention_days":180}'::jsonb, 'Ejecucion demo de limpieza programada.')
ON CONFLICT DO NOTHING;
