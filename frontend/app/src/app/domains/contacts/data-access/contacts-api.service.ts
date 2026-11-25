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

export interface ContactDetail extends Contact {
  normalized_email?: string | null;
  normalized_phone?: string | null;
}

export interface ContactPoints { email: string | null; phone: string | null; }
export interface ContactDraft extends ContactPoints { full_name: string; request_id: string; }

export interface ConsentEvidenceItem {
  id: number;
  kind: 'decision' | 'prior_withdrawal';
  accepted: boolean | null;
  effective_at: string | null;
  recorded_at: string;
  policy_version: string | null;
  source: 'whatsapp_message' | 'operational' | null;
}

export interface ContactConsent {
  channel: 'whatsapp';
  state: 'unlinked' | 'unrecorded' | 'granted' | 'not_granted';
  decision_at: string | null;
  authorized_from: string | null;
  policy_version: string | null;
  items: ConsentEvidenceItem[];
  next_before_id: number | null;
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
    return this.http.get<ApiResponse<ContactDetail>>(`${OPERATIONAL_API_BASE_URL}/contacts/${encodeURIComponent(id)}`)
      .pipe(map(({ data }) => data));
  }

  whatsappConsent(id: number, beforeId?: number) {
    return this.http.get<ApiResponse<ContactConsent>>(`${OPERATIONAL_API_BASE_URL}/contacts/${id}/whatsapp-consent`, {
      params: toParams({ before_id: beforeId })
    }).pipe(map(({ data }) => data));
  }

  create(draft: ContactDraft) {
    return this.http.post<ApiResponse<{ contact: ContactDetail; created: boolean }>>(`${OPERATIONAL_API_BASE_URL}/contacts`, draft)
      .pipe(map(({ data }) => data));
  }

  updatePoints(contact: Contact, points: ContactPoints) {
    return this.http.patch<ApiResponse<ContactDetail>>(`${OPERATIONAL_API_BASE_URL}/contacts/${contact.id}/points`, {
      ...points, expected_email: contact.email, expected_phone: contact.phone
    }).pipe(map(({ data }) => data));
  }

  rename(id: number, fullName: string, expectedName: string) {
    return this.http.patch<ApiResponse<Contact>>(`${OPERATIONAL_API_BASE_URL}/contacts/${id}`, {
      full_name: fullName, expected_full_name: expectedName
    }).pipe(map(({ data }) => data));
  }
}
