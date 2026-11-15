# Permissions

Un agente de programacion puede:

- Crear codigo, tests y documentacion dentro de este repositorio.
- Ejecutar tests locales.
- Proponer cambios de modelo transversal documentados para que operational los migre.
- Actualizar skills de mantenimiento.

Requiere aprobacion humana:

- Instalar dependencias con red.
- Cambiar contratos publicos.
- Tocar secretos, llaves, `.env`, dominios, CI/CD o infraestructura.
- Ejecutar migraciones destructivas o DDL directo desde este servicio.
- Habilitar acciones externas reales.

Prohibido:

- Exponer secretos.
- Copiar datos personales reales a docs/tests.
- Mezclar datos de tenants.
- Agregar logica especifica de WhatsApp, Instagram, Facebook o TikTok dentro del core.
