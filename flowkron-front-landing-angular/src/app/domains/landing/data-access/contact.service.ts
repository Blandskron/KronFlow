import { HttpClient, HttpHeaders } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { map, Observable, switchMap } from 'rxjs';
import { environment } from '@env/environment';

export interface ContactPayload {
  name: string;
  email: string;
  company: string;
  phone: string;
  message: string;
  accept_terms: boolean;
}

interface ApiEnvelope<T> {
  success: boolean;
  data: T;
}

interface CsrfResponse {
  csrfToken: string;
}

interface ContactResponse {
  id: number;
  created_at: string;
}

@Injectable({ providedIn: 'root' })
export class ContactService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = environment.contactApiBaseUrl.replace(/\/$/, '');

  send(payload: ContactPayload): Observable<ContactResponse> {
    return this.csrfToken().pipe(
      switchMap((csrfToken) =>
        this.http
          .post<ApiEnvelope<ContactResponse>>(`${this.baseUrl}/api/v1/contact/messages/`, payload, {
            headers: new HttpHeaders({ 'X-CSRFToken': csrfToken }),
            withCredentials: true
          })
          .pipe(map((response) => response.data))
      )
    );
  }

  private csrfToken(): Observable<string> {
    return this.http
      .get<ApiEnvelope<CsrfResponse>>(`${this.baseUrl}/api/v1/contact/csrf/`, { withCredentials: true })
      .pipe(map((response) => response.data.csrfToken));
  }
}
