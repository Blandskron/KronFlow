# Autenticación

**Versión:** 1.0
**Tipo:** Estado actual
**Última verificación:** 2026-06-22

## Autoridad de identidad

`flowkron-auth-service` es la autoridad de identidad. Está implementado con Django REST Framework y emite tokens RS256.

## Flujos implementados

- registro, verificación de correo e inicio/cierre de sesión;
- renovación de sesión y recuperación/cambio de contraseña;
- MFA TOTP;
- autenticación con Google;
- credenciales de cliente para comunicación de servicios;
- inspección de sesión y administración IAM según permisos.

## Tokens

Existen dos familias con propósitos distintos:

- **tokens de usuario:** acceso de 10 minutos y refresh de 14 días;
- **tokens de servicio:** emitidos mediante credenciales de cliente y destinados a comunicación máquina a máquina.

El servicio operacional valida la firma con la clave pública compartida. El modelo completo de audiencias, rotación, revocación y propagación entre servicios continúa pendiente de una decisión formal; véase [ADR-005](../04-architecture/technical-decisions-adr/ADR-005-jwt-trust-model.md).

## Cliente web

La aplicación Angular integra los flujos anteriores y adjunta el access token a las APIs. Actualmente persiste tokens en `localStorage`; esto es una decisión implementada, no una recomendación de arquitectura objetivo.

## Evidencia y límites

El servicio IAM posee pruebas automatizadas. La integración de sesión del frontend y la validación extremo a extremo del stack no cuentan con una suite automatizada equivalente. No debe afirmarse SSO empresarial, autenticación adaptativa ni revocación global inmediata: no están implementados.
