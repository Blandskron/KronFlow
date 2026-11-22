import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';
import { OPERATIONAL_API_BASE_URL } from '@core/config/api.config';
import { ApiResponse, PaginatedResponse } from '@shared/types/api.types';
import { Conversation, ConversationCursor, ConversationMessage, PendingReply } from '../domain/conversation.model';
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
    before_at?: string;
    before_id?: number;
    q?: string;
    contact_id?: number;
  } = {}): Observable<PaginatedResponse<Conversation> & { next_cursor?: ConversationCursor | null }> {
    return this.http
      .get<ApiResponse<PaginatedResponse<Conversation> & { next_cursor?: ConversationCursor | null }>>(`${OPERATIONAL_API_BASE_URL}/conversations`, {
        params: toParams(filters)
      })
      .pipe(map((response) => response.data));
  }

  getConversation(conversationId: number): Observable<Conversation> {
    return this.http.get<ApiResponse<Conversation>>(`${OPERATIONAL_API_BASE_URL}/conversations/${conversationId}`)
      .pipe(map((response) => response.data));
  }

  markRead(conversationId: number, throughMessageId: number): Observable<{ no_leidos: number }> {
    return this.http.post<ApiResponse<{ no_leidos: number }>>(
      `${OPERATIONAL_API_BASE_URL}/conversations/${conversationId}/read`,
      { through_message_id: throughMessageId }
    ).pipe(map((response) => response.data));
  }

  listMessages(conversationId: number, beforeId?: number): Observable<PaginatedResponse<ConversationMessage> & { pending_replies?: PendingReply[] }> {
    return this.http
      .get<ApiResponse<PaginatedResponse<ConversationMessage> & { pending_replies?: PendingReply[] }>>(
        `${OPERATIONAL_API_BASE_URL}/conversations/${conversationId}/messages`,
        { params: toParams({ limit: 50, order: 'recent', before_id: beforeId }) }
      )
      .pipe(map((response) => response.data));
  }
}
