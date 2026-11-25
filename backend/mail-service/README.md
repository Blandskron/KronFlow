# KronFlow Mail Service (`backend/mail-service`)

KronFlow / BLANDSKRON Email Gateway es una API FastAPI centralizada para correo transaccional. Recibe solicitudes autenticadas, valida el remitente autorizado y envía mediante la API HTTPS de Resend. No acepta ni utiliza credenciales SMTP.

El proceso no mantiene datos de negocio, pero la idempotencia sí requiere estado:
usa Redis cuando `REDIS_URL` está configurado y memoria local en caso contrario.
Producción y despliegues con más de una réplica deben usar Redis compartido.

## Flujo

```text
Consumidor -> Bearer interno -> Email Gateway -> Resend HTTPS -> Destinatarios
```

## Endpoints

| Método | Ruta | Seguridad | Descripción |
| --- | --- | --- | --- |
| GET | `/health` | Pública | Proceso vivo. |
| GET | `/ready` | Pública | Configuración operativa sin secretos. |
| POST | `/api/v1/emails/send` | Bearer interno | Envío idempotente mediante Resend. |
| POST | `/api/v1/webhooks/resend` | Firma Svix/Resend | Eventos del proveedor. |
| POST | `/mail` | Bearer interno | Legacy deprecated, desactivable. |

OpenAPI está disponible en `/docs` y `/openapi.json`.

## Instalación local

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

La API Key de Resend solo debe existir en `.env` o en el gestor de secretos del despliegue. Configura también `EMAIL_SENDERS_JSON` e `INTERNAL_CLIENTS_JSON`.

Las cuatro piezas deben ser coherentes:

```text
MAIL_INTERNAL_API_KEY (consumidor)
  = INTERNAL_CLIENTS_JSON.<cliente>.api_key (gateway)
MAIL_SENDER_KEY (consumidor)
  pertenece a INTERNAL_CLIENTS_JSON.<cliente>.allowed_senders
MAIL_SENDER_KEY
  existe en EMAIL_SENDERS_JSON
RESEND_API_KEY
  = credencial válida del proveedor
```

`GET /health` solo confirma que el proceso está vivo. Usa `GET /ready` para habilitar envíos: responde `503` mientras falten proveedor, remitentes o clientes internos. Un contenedor con `/health` en `200` no garantiza entrega de correo.

## Consumo

El consumidor utiliza `Authorization: Bearer` con su credencial interna y solo envía `sender_key`, destinatarios, contenido e idempotencia. Nunca envía servidor, puerto, usuario, contraseña ni remitente arbitrario.

```bash
curl --request POST \\
  --url http://127.0.0.1:8000/api/v1/emails/send \\
  --header "Authorization: Bearer ${MAIL_INTERNAL_API_KEY}" \\
  --header "Content-Type: application/json" \\
  --data '{"sender_key":"blandskron","to":["destinatario@example.com"],"subject":"Prueba","html":"<p>Contenido</p>","text":"Contenido","idempotency_key":"operacion-001"}'
```

## CLI controlada

```powershell
python -m app.cli.test_email --sender-key blandskron --to delivered@resend.dev
```

La CLI usa el mismo proveedor y no muestra credenciales.

## Docker y Railway

```powershell
docker build -t blandskron-email-gateway .
docker run --env-file .env -p 8000:8000 blandskron-email-gateway
```

Railway debe ejecutar Uvicorn en `0.0.0.0` usando `PORT`, y configurar las variables secretas en Railway. `passenger_wsgi.py` se conserva únicamente para instalaciones Passenger existentes; no es el método principal de Railway.

## Pruebas

```powershell
pytest -q
```

Las pruebas mockean el proveedor y cubren autenticación, autorización de remitente, payload estricto, idempotencia, readiness, legacy y firma de webhooks.

La deduplicación de webhooks Resend usa actualmente memoria de proceso. Se pierde
al reiniciar y no se comparte entre réplicas; antes de escalar debe moverse a un
almacenamiento compartido con TTL.

## Migración SMTP

Se eliminó el contrato que recibía host, puerto, usuario, contraseña y remitente. El endpoint legacy acepta únicamente el payload camelCase de transición sin credenciales SMTP y puede desactivarse con `ENABLE_LEGACY_MAIL_ENDPOINT=false`.
