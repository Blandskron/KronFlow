import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';
import { OPERATIONAL_API_BASE_URL } from '@core/config/api.config';
import { ApiResponse, PaginatedResponse } from '@shared/types/api.types';
import {
  Conversation,
  ConversationControl,
  ConversationCursor,
  ConversationMessage,
  HandoffHistoryPage,
  AgentHandoffItem,
  HumanReplyResult,
  PendingReply
} from '../domain/conversation.model';
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

  handoffHistory(beforeId?: number): Observable<HandoffHistoryPage> {
    return this.http.get<ApiResponse<HandoffHistoryPage>>(`${OPERATIONAL_API_BASE_URL}/conversations/handoff-history`, {
      params: toParams({ before_id: beforeId })
    }).pipe(map(({ data }) => data));
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

  getControl(conversationId: number): Observable<ConversationControl> {
    return this.http
      .get<ApiResponse<ConversationControl>>(`${OPERATIONAL_API_BASE_URL}/conversations/${conversationId}/control`)
      .pipe(map((response) => response.data));
  }

  claimConversation(conversationId: number, expectedVersion: number, reason?: string): Observable<ConversationControl> {
    return this.http
      .post<ApiResponse<ConversationControl>>(`${OPERATIONAL_API_BASE_URL}/conversations/${conversationId}/claim`, {
        expected_version: expectedVersion,
        reason
      })
      .pipe(map((response) => response.data));
  }

  sendHumanReply(conversationId: number, body: string, idempotencyKey: string): Observable<HumanReplyResult> {
    return this.http
      .post<ApiResponse<HumanReplyResult>>(`${OPERATIONAL_API_BASE_URL}/conversations/${conversationId}/messages`, {
        body,
        idempotency_key: idempotencyKey
      })
      .pipe(map((response) => response.data));
  }

  returnToAi(conversationId: number, expectedVersion: number, reason?: string): Observable<ConversationControl> {
    return this.http
      .post<ApiResponse<ConversationControl>>(`${OPERATIONAL_API_BASE_URL}/conversations/${conversationId}/return-to-ai`, {
        expected_version: expectedVersion,
        reason
      })
      .pipe(map((response) => response.data));
  }

  listAgentHandoffs(conversationId: number): Observable<AgentHandoffItem[]> {
    return this.http
      .get<ApiResponse<AgentHandoffItem[]>>(`${OPERATIONAL_API_BASE_URL}/conversations/${conversationId}/agent-handoffs`)
      .pipe(map((response) => response.data));
  }

  handoffToAgent(
    conversationId: number,
    payload: { target_agent_id: number; reason: string; shared_summary?: string }
  ): Observable<AgentHandoffItem> {
    return this.http
      .post<ApiResponse<AgentHandoffItem>>(`${OPERATIONAL_API_BASE_URL}/conversations/${conversationId}/agent-handoff`, payload)
      .pipe(map((response) => response.data));
  }

  resolveConversation(conversationId: number, expectedVersion: number, reason: string): Observable<ConversationControl> {
    return this.http
      .post<ApiResponse<ConversationControl>>(`${OPERATIONAL_API_BASE_URL}/conversations/${conversationId}/resolve`, {
        expected_version: expectedVersion,
        reason
      })
      .pipe(map((response) => response.data));
  }
}
