# Recuperación ante desastres

**Versión:** 1.0
**Tipo:** `NOT_IMPLEMENTED`
**Última verificación:** 2026-06-22

No se encontraron backups automatizados, restauraciones probadas, réplica, alta disponibilidad, infraestructura reconstruible fuera del Compose local ni runbook de desastre. Reiniciar un contenedor no cubre pérdida del host, corrupción o eliminación de datos.

## Alcance requerido

1. inventariar PostgreSQL, Redis si aplica, claves JWT, medios, secretos y artefactos;
2. acordar RPO/RTO con responsables de negocio y riesgo;
3. automatizar copias cifradas fuera del host y verificar su integridad;
4. documentar reconstrucción de infraestructura y restauración de cada activo;
5. ejecutar ejercicios periódicos y registrar tiempos/resultados;
6. definir comunicación, escalamiento y criterios de retorno al servicio.

La política técnica de respaldo se detalla en [Estado de respaldos](../06-security-compliance/06-backup-policy.md). Hasta validacionstrar una restauración, no debe declararse capacidad de disaster recovery.
