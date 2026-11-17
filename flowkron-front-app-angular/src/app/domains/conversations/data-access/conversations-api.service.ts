import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';
import { OPERATIONAL_API_BASE_URL } from '@core/config/api.config';
import { ApiResponse, PaginatedResponse } from '@shared/types/api.types';
import { Conversation, ConversationMessage } from '../domain/conversation.model';
import { toParams } from '@shared/utils/http.utils';

@Injectable({ providedIn: 'root' })
export class ConversationsApiService {
  private readonly http = inject(HttpClient);

  listConversations(filters: {
    status?: string;
    channel?: string;
    requires_human?: boolean;
    limit?: number;
    offset?: number;
  } = {}): Observable<PaginatedResponse<Conversation>> {
    return this.http
      .get<ApiResponse<PaginatedResponse<Conversation>>>(`${OPERATIONAL_API_BASE_URL}/conversations`, {
        params: toParams(filters)
      })
      .pipe(map((response) => response.data));
  }

  listMessages(conversationId: number, beforeId?: number): Observable<PaginatedResponse<ConversationMessage>> {
    return this.http
      .get<ApiResponse<PaginatedResponse<ConversationMessage>>>(
        `${OPERATIONAL_API_BASE_URL}/conversations/${conversationId}/messages`,
        { params: toParams({ limit: 50, order: 'recent', before_id: beforeId }) }
      )
      .pipe(map((response) => response.data));
  }
}
