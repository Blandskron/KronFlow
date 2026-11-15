# Flowkron Baileys Services

Conector de laboratorio para vincular por QR una cuenta de WhatsApp como dispositivo asociado. Corre una sesión por instancia y admite ingesta de texto con credenciales de un tenant de Operational.

## Ejecutar el piloto

Desde la raíz, copia `.env.example` a `.env` si no tienes uno. Genera un secreto de al menos 32 caracteres para `BAILEYS_INTERNAL_TOKEN`. Deja vacías las dos variables de ingesta para probar únicamente el vínculo.

```powershell
docker compose --profile whatsapp-lab up -d --build flowkron-baileys-services
```

El servicio escucha en el puerto interno 3001. Usa `Authorization: Bearer <BAILEYS_INTERNAL_TOKEN>` para los endpoints de sesión.

| Método y ruta | Resultado |
| --- | --- |
| `GET /health` | Confirma que el proceso HTTP responde. |
| `POST /internal/baileys/session/start` | Inicia el vínculo o abre la sesión guardada. Devuelve `202` y el estado, o `409` si hace falta una sesión nueva. |
| `GET /internal/baileys/session` | Devuelve el estado y, si está pendiente, un QR PNG como data URL. |

Inicia la conexión desde el contenedor de laboratorio:

```powershell
docker compose --profile whatsapp-lab exec -T flowkron-baileys-services node -e 'fetch("http://127.0.0.1:3001/internal/baileys/session/start",{method:"POST",headers:{Authorization:"Bearer "+process.env.BAILEYS_INTERNAL_TOKEN}}).then(async r=>{console.log(await r.json());if(!r.ok) process.exitCode=1})'
```

Consulta el estado y abre el código en un archivo temporal. Escanéalo desde **Dispositivos vinculados** con una cuenta de laboratorio bajo tu control. Elimina el archivo al terminar.

```powershell
$flowPairing = docker compose --profile whatsapp-lab exec -T flowkron-baileys-services node -e 'fetch("http://127.0.0.1:3001/internal/baileys/session",{headers:{Authorization:"Bearer "+process.env.BAILEYS_INTERNAL_TOKEN}}).then(r=>r.text()).then(console.log)' | ConvertFrom-Json
$flowPairing.status
if ($flowPairing.qr) {
  $flowPairingFile = Join-Path $env:TEMP ('flowkron-whatsapp-' + [guid]::NewGuid() + '.png')
  [IO.File]::WriteAllBytes($flowPairingFile, [Convert]::FromBase64String(($flowPairing.qr -split ',', 2)[1]))
  Invoke-Item -LiteralPath $flowPairingFile
}
```

Repite la consulta hasta ver `connected`. El volumen privado `baileys-lab-sessions` conserva las credenciales. Tras reiniciar el servicio, llama a `session/start` para recuperar la conexión. Si el estado es `pairing_required`, desvincula el dispositivo desde el teléfono y usa un volumen nuevo para el piloto. Ejecuta cada sesión en una sola instancia y protege el volumen como una credencial.

## Habilitar la ingesta

Configura conjuntamente `BAILEYS_INGEST_TENANT_CODE` y `BAILEYS_INGEST_KEY` con las credenciales del tenant de laboratorio provisionado en Operational. Levanta Operational y recrea el conector. El piloto verifica el consentimiento registrado antes de enviar texto entrante al endpoint de ingesta. Usa participantes autorizados con consentimiento registrado. Los errores de red se registran de forma genérica. La ingesta de laboratorio es de mejor esfuerzo.

Las comprobaciones locales usan Node 24 y eventos simulados.

```powershell
npm ci
npm test
npm audit --omit=dev
```

La conexión en el CRM, la respuesta del agente, la cola de eventos y las campañas están diseñadas en el [informe de investigación](../flowkron-product-docs/04-architecture/14-whatsapp-connection-and-campaigns.md).
