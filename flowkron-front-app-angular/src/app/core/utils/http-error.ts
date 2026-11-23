import { HttpErrorResponse } from '@angular/common/http';

interface ErrorEnvelope {
  error?: { message?: string; code?: string };
  detail?: string;
  message?: string;
}

/**
 * Extracts a safe, user-facing Spanish error message from any HTTP or runtime error.
 */
export function extractHttpErrorMessage(error: unknown, fallback = 'Ocurrió un error inesperado. Intenta nuevamente.'): string {
  if (error instanceof HttpErrorResponse) {
    const body = error.error;
    if (typeof body === 'string' && body.trim()) {
      return body.trim();
    }
    if (body && typeof body === 'object') {
      const envelope = body as ErrorEnvelope;
      const candidate = envelope.error?.message ?? envelope.detail ?? envelope.message;
      if (typeof candidate === 'string' && candidate.trim()) {
        return candidate.trim();
      }
    }
    if (error.status === 0) {
      return 'No se pudo conectar con el servidor. Verifica tu conexión.';
    }
  }

  if (error instanceof Error && error.message.trim()) {
    return error.message.trim();
  }

  return fallback;
}
