# Prueba manual de seguimiento comercial

Usa un proyecto demo local descartable y conserva WhatsApp desconectado. Puedes empezar desde la interfaz con un contacto sintético de tu empresa de QA. [Instalación demo](../../../README.md#start-the-demo)

## Crear el contacto desde la interfaz

1. En **Contactos**, elige **Nuevo contacto** con una cuenta que tenga `crm.manage` e ingresa **Contacto QA desde interfaz**. Puedes dejar correo y teléfono vacíos o usar `Contacto+qa@EXAMPLE.TEST` y `+56 9 1234 5678` como muestra.
2. Guarda y verifica que se abra la nueva ficha. Si ingresaste los datos de ejemplo, verás `Contacto+qa@example.test` y `+56912345678`. Si el alta queda sin confirmar, el botón **Reintentar alta** vuelve a enviar la misma solicitud.
3. En **Editar datos de contacto**, borra un campo y guarda. Recarga la página y verifica que el campo siga vacío. Para probar un conflicto, abre el mismo contacto en dos pestañas y edita en cada una valores distintos. Tras guardar la primera, la segunda debe pedir recargar antes de guardar.
4. Continúa con **Iniciar seguimiento** y los pasos del recorrido comercial.

## Fixture SQL opcional para las pruebas de Notificaciones

Desde la raíz del repositorio y con la demo iniciada, consulta el schema de tu empresa y carga el fixture. Los comandos usan el usuario, la base y el schema operacional predeterminados de la demo. Si tu instalación los modificó, usa sus valores locales.

```powershell
docker compose -f compose.demo.yaml exec -T flowkron-postgres psql -X -U flowkron_admin -d flowkron_auth `
  -c 'SELECT tenant_slug, schema_name FROM operational.tenant_runtime WHERE status = ''active'';'

$qaSchema = 'tenant_REEMPLAZAR'
Get-Content -Raw flowkron-operational-service/tests/fixtures/manual_lead_qa.sql |
  docker compose -f compose.demo.yaml exec -T flowkron-postgres psql -X -U flowkron_admin -d flowkron_auth `
    -v ON_ERROR_STOP=1 -v "tenant_schema=$qaSchema"
```

Sustituye `tenant_REEMPLAZAR` por el schema exacto que mostró la consulta. Puedes volver a cargar el fixture. Si el contacto ya existe, conserva los cambios y el lead de la prueba anterior.

## Recorrido y resultados esperados

| Paso | Resultado esperado |
| --- | --- |
| En **Contactos**, abre el contacto que acabas de crear o **Contacto QA sin lead** si usaste el fixture. | La sección de leads está vacía en la primera ejecución. Un operador con `crm.manage` ve **Iniciar seguimiento**. |
| Pulsa **Iniciar seguimiento** y vuelve a abrir el contacto desde el lead. | Aparece un solo lead vinculado, con etapa **Nuevo** y temperatura **Frío**. Si vuelves a la ficha, el enlace abre ese mismo lead. |
| Cambia la etapa a **Contactado** y la temperatura a **Tibio**. Guarda y recarga. | Se conservan ambos valores. Con `audit.read`, el historial contiene el alta y los dos cambios con sus valores previos y nuevos. |
| Abre el mismo lead en dos pestañas. Guarda un cambio en la primera y luego intenta guardar en la segunda. | La segunda muestra el conflicto y recupera los valores actuales. Selecciona de nuevo el cambio si corresponde y confirma. |
| Vuelve a **Seguimiento**. Filtra por **Tibio**, abre el lead y pulsa **Volver a seguimiento**. | Se conserva el filtro y la búsqueda de esa pestaña. El resultado se actualiza si el lead cambió de temperatura. |
| Abre el lead con un usuario que solo tenga `users.read`. | Puede leer la ficha. La edición y el historial quedan sujetos a `crm.manage` y `audit.read`, respectivamente. |
| Abre la URL del lead en otra empresa de QA donde ese ID no exista. | La ficha muestra que no se encontró el lead. Si esa empresa tiene un lead con el mismo ID, muestra exclusivamente su registro. |

Para registrar una prueba, anota el SHA, el paso, el resultado y el rol del usuario. El recorrido prepara seguimiento sobre un contacto existente. La oportunidad independiente, la captura pública y los envíos siguen sus propios casos de aceptación. [Alcance y dependencias](03-inbound-crm.md)
