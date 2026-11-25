import { HttpParams } from '@angular/common/http';

export function toParams(filters: Record<string, string | number | boolean | undefined>): HttpParams {
  let params = new HttpParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      params = params.set(key, String(value));
    }
  });
  return params;
}
