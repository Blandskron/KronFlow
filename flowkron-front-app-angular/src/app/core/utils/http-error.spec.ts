import { HttpErrorResponse } from '@angular/common/http';
import { extractHttpErrorMessage } from './http-error';

describe('extractHttpErrorMessage', () => {
  it('extracts message from KronFlow error envelope', () => {
    const err = new HttpErrorResponse({
      status: 400,
      error: { error: { code: 'INVALID', message: 'Campo inválido' } }
    });
    expect(extractHttpErrorMessage(err)).toBe('Campo inválido');
  });

  it('extracts FastAPI detail message', () => {
    const err = new HttpErrorResponse({ status: 422, error: { detail: 'Documento demasiado grande' } });
    expect(extractHttpErrorMessage(err)).toBe('Documento demasiado grande');
  });

  it('returns offline message for status 0', () => {
    const err = new HttpErrorResponse({ status: 0 });
    expect(extractHttpErrorMessage(err)).toContain('conectar con el servidor');
  });

  it('returns fallback for unknown values', () => {
    expect(extractHttpErrorMessage(null, 'Fallo personalizado')).toBe('Fallo personalizado');
  });
});
