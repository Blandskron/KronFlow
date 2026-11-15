import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, effect, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import {
  LucideArrowLeft,
  LucideFilter,
  LucideMail,
  LucideMessageSquare,
  LucidePhone,
  LucideRefreshCw,
  LucideSearch
} from '@lucide/angular';
import { Conversation, ConversationMessage } from '@domains/conversations/domain/conversation.model';
import { AuthService } from '@domains/auth/data-access/auth-api.service';
import { ConversationsApiService } from '@domains/conversations/data-access/conversations-api.service';

type ChatStatus = 'new' | 'active' | 'waiting' | 'closed';
type LeadStatus = 'cold' | 'warm' | 'hot' | 'converted';

interface ChatContact {
  id: number;
  name: string;
  lastMessage: string;
  timestamp: string;
  status: ChatStatus;
  channel: 'whatsapp' | 'email' | 'web';
  leadStatus: LeadStatus;
  unreadCount?: number;
}

interface Message {
  id: number;
  sender: 'user' | 'agent';
  text: string;
  timestamp: string;
}

@Component({
  selector: 'flowkron-chats-page',
  standalone: true,
  imports: [
    LucideArrowLeft,
    LucideFilter,
    LucideMail,
    LucideMessageSquare,
    LucidePhone,
    LucideRefreshCw,
    LucideSearch,
    RouterLink
  ],
  templateUrl: './chats-page.component.html',
  styleUrl: './chats-page.component.css'
})
export class ChatsPageComponent implements OnInit {
  readonly auth = inject(AuthService);
  private readonly operational = inject(ConversationsApiService);

  readonly searchQuery = signal('');
  readonly filterStatus = signal('all');
  readonly selectedChat = signal<ChatContact | null>(null);
  readonly messageInput = signal('');
  readonly isLoading = signal(false);
  readonly loadError = signal('');
  readonly chats = signal<ChatContact[]>([]);
  readonly conversations = signal<Record<number, Message[]>>({});
  readonly planRequired = signal(false);
  readonly hasLoaded = signal(false);
  readonly requiresPlan = computed(() => Boolean(this.auth.subscription()?.requires_paid_plan || this.planRequired()));

  readonly statuses = [
    { id: 'all', label: 'Todos' },
    { id: 'new', label: 'Nuevo' },
    { id: 'active', label: 'Activo' },
    { id: 'waiting', label: 'Esperando' },
    { id: 'closed', label: 'Cerrado' }
  ];

  readonly filteredChats = computed(() => {
    const query = this.searchQuery().toLowerCase().trim();
    const status = this.filterStatus();
    return this.chats().filter((chat) => {
      const matchesQuery = !query || chat.name.toLowerCase().includes(query) || chat.lastMessage.toLowerCase().includes(query);
      const matchesStatus = status === 'all' || chat.status === status;
      return matchesQuery && matchesStatus;
    });
  });

  constructor() {
    effect(() => {
      if (!this.auth.subscription()?.requires_paid_plan && this.planRequired()) {
        setTimeout(() => this.planRequired.set(false));
      }

      if (!this.requiresPlan() && !this.isLoading() && !this.hasLoaded() && !this.loadError()) {
        setTimeout(() => this.loadConversations());
      }
    });
  }

  ngOnInit(): void {
    if (this.requiresPlan()) {
      this.chats.set([]);
      return;
    }

    this.loadConversations();
  }

  loadConversations(): void {
    if (this.requiresPlan()) {
      this.chats.set([]);
      this.loadError.set('');
      this.isLoading.set(false);
      return;
    }

    this.isLoading.set(true);
    this.loadError.set('');
    this.operational.listConversations({ limit: 100 }).subscribe({
      next: (response) => {
        this.chats.set(response.items.map((item) => this.toChatContact(item)));
        this.hasLoaded.set(true);
        this.isLoading.set(false);
      },
      error: (error) => {
        if (this.isPlanAccessError(error)) {
          this.planRequired.set(true);
          this.chats.set([]);
          this.loadError.set('');
          this.hasLoaded.set(true);
        } else {
          this.loadError.set(this.operationalErrorMessage(error));
        }
        this.isLoading.set(false);
      }
    });
  }

  select(chatId: number): void {
    const chat = this.chats().find((item) => item.id === chatId) ?? null;
    this.selectedChat.set(chat);
    if (!chat || this.conversations()[chat.id]) {
      return;
    }
    this.operational.listMessages(chat.id).subscribe({
      next: (response) => {
        this.conversations.update((current) => ({
          ...current,
          [chat.id]: response.items.map((message) => this.toMessage(message))
        }));
      },
      error: () => {
        this.conversations.update((current) => ({ ...current, [chat.id]: [] }));
      }
    });
  }

  messagesFor(chatId: number): Message[] {
    return this.conversations()[chatId] ?? [];
  }

  channelLabel(channel: ChatContact['channel']): string {
    return channel === 'web' ? 'Web Chat' : channel === 'email' ? 'Email' : 'WhatsApp';
  }

  statusLabel(status: ChatStatus): string {
    return { new: 'Nuevo', active: 'Activo', waiting: 'Esperando', closed: 'Cerrado' }[status];
  }

  leadLabel(status: LeadStatus): string {
    return { cold: 'Frio', warm: 'Tibio', hot: 'Caliente', converted: 'Convertido' }[status];
  }

  statusClass(status: ChatStatus): string {
    return status === 'new' ? 'badge-info' : status === 'active' ? 'badge-success' : status === 'waiting' ? 'badge-warning' : 'badge-primary';
  }

  leadClass(status: LeadStatus): string {
    return status === 'hot' ? 'badge-danger' : status === 'converted' ? 'badge-success' : status === 'warm' ? 'badge-warning' : 'badge-info';
  }

  private toChatContact(conversation: Conversation): ChatContact {
    return {
      id: conversation.id,
      name: conversation.lead_name || conversation.lead_phone || 'Lead sin nombre',
      lastMessage: conversation.last_message || 'Sin mensajes registrados',
      timestamp: this.formatRelative(conversation.last_message_at || conversation.updated_at),
      status: this.mapConversationStatus(conversation),
      channel: this.mapChannel(conversation.channel),
      leadStatus: this.mapLeadStatus(conversation.temperature),
      unreadCount: conversation.requires_human ? 1 : undefined
    };
  }

  private toMessage(message: ConversationMessage): Message {
    return {
      id: message.id,
      sender: message.sender_type === 'lead' ? 'user' : 'agent',
      text: message.body,
      timestamp: this.formatTime(message.sent_at)
    };
  }

  private mapConversationStatus(conversation: Conversation): ChatStatus {
    if (conversation.requires_human) {
      return 'waiting';
    }
    if (conversation.status === 'closed') {
      return 'closed';
    }
    if (conversation.status === 'new') {
      return 'new';
    }
    return 'active';
  }

  private mapLeadStatus(status: string | null): LeadStatus {
    if (status === 'hot') {
      return 'hot';
    }
    if (status === 'warm') {
      return 'warm';
    }
    if (status === 'converted') {
      return 'converted';
    }
    return 'cold';
  }

  private mapChannel(channel: string): ChatContact['channel'] {
    return channel === 'email' ? 'email' : channel === 'web' || channel === 'webchat' ? 'web' : 'whatsapp';
  }

  private formatTime(value: string): string {
    return new Intl.DateTimeFormat('es-CL', { hour: '2-digit', minute: '2-digit' }).format(new Date(value));
  }

  private formatRelative(value: string): string {
    const date = new Date(value);
    const diffMinutes = Math.max(0, Math.round((Date.now() - date.getTime()) / 60000));
    if (diffMinutes < 1) {
      return 'Ahora';
    }
    if (diffMinutes < 60) {
      return `Hace ${diffMinutes} min`;
    }
    const diffHours = Math.round(diffMinutes / 60);
    if (diffHours < 24) {
      return `Hace ${diffHours} h`;
    }
    return new Intl.DateTimeFormat('es-CL', { day: '2-digit', month: 'short' }).format(date);
  }

  private isPlanAccessError(error: unknown): boolean {
    return error instanceof HttpErrorResponse && error.status === 402;
  }

  private operationalErrorMessage(error: unknown): string {
    if (!(error instanceof HttpErrorResponse)) {
      return 'No pudimos cargar las conversaciones del servicio operacional.';
    }
    if (error.status === 401) {
      return 'Tu sesion expiro o no pudo validarse con operational. Vuelve a iniciar sesion.';
    }
    if (error.status === 403) {
      return 'El tenant no tiene acceso operacional activo o esta suspendido.';
    }
    if (error.status === 404) {
      return 'El entorno operacional del tenant aun no esta provisionado.';
    }
    return 'No pudimos cargar las conversaciones del servicio operacional.';
  }
}
