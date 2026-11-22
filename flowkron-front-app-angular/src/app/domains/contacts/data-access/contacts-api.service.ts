import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { OPERATIONAL_API_BASE_URL } from '@core/config/api.config';
import { ApiResponse, PaginatedResponse } from '@shared/types/api.types';
import { toParams } from '@shared/utils/http.utils';
import { map } from 'rxjs';

export interface Contact {
  id: number;
  full_name: string;
  email: string | null;
  phone: string | null;
  source: string;
  created_at: string;
}

@Injectable({ providedIn: 'root' })
export class ContactsApiService {
  private readonly http = inject(HttpClient);

  list(q: string, source: string, limit: number, offset: number) {
    return this.http.get<ApiResponse<PaginatedResponse<Contact>>>(`${OPERATIONAL_API_BASE_URL}/contacts`, {
      params: toParams({ q, source, limit, offset })
    }).pipe(map(({ data }) => data));
  }

  sources() {
    return this.http.get<ApiResponse<string[]>>(`${OPERATIONAL_API_BASE_URL}/contacts/sources`).pipe(map(({ data }) => data));
  }

  get(id: string) {
    return this.http.get<ApiResponse<Contact>>(`${OPERATIONAL_API_BASE_URL}/contacts/${encodeURIComponent(id)}`)
      .pipe(map(({ data }) => data));
  }
}
