import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, ElementRef, Injector, OnInit, afterNextRender, computed, inject, signal, viewChild } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute } from '@angular/router';
import { timer } from 'rxjs';
import {
  LucideArrowLeft,
  LucideMail,
  LucideMessageSquare,
  LucidePhone,
  LucideRefreshCw,
  LucideSearch
} from '@lucide/angular';
import { Conversation, ConversationMessage } from '@domains/conversations/domain/conversation.model';
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
  requiresHuman: boolean;
}

interface Message {
  id: number;
  sender: 'user' | 'agent';
  text: string;
  timestamp: string;
}

interface Thread {
  loading: boolean;
  error: boolean;
  hasOlder: boolean;
  messages: Message[];
}

@Component({
  selector: 'flowkron-chats-page',
  standalone: true,
  imports: [
    LucideArrowLeft,
    LucideMail,
    LucideMessageSquare,
    LucidePhone,
    LucideRefreshCw,
    LucideSearch
  ],
  templateUrl: './chats-page.component.html',
  styleUrl: './chats-page.component.css'
})
export class ChatsPageComponent implements OnInit {
  private readonly operational = inject(ConversationsApiService);
  private readonly injector = inject(Injector);
  private readonly destroyRef = inject(DestroyRef);
  private readonly route = inject(ActivatedRoute);
  private readonly backButton = viewChild<ElementRef<HTMLButtonElement>>('backButton');

  readonly searchQuery = signal('');
  readonly filterStatus = signal('all');
  readonly selectedChatId = signal<number | null>(null);
  readonly selectedChat = computed(() => this.chats().find((chat) => chat.id === this.selectedChatId()) ?? null);
  readonly isLoading = signal(false);
  readonly loadError = signal('');
  readonly chats = signal<ChatContact[]>([]);
  readonly threads = signal<Partial<Record<number, Thread>>>({});

  readonly statuses = [
    { id: 'all', label: 'Todas' },
    { id: 'new', label: 'Nuevas' },
    { id: 'active', label: 'Activas' },
    { id: 'waiting', label: 'Necesitan atención' },
    { id: 'closed', label: 'Cerradas' }
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

  ngOnInit(): void {
    const requested = Number(this.route.snapshot.queryParamMap.get('conversation'));
    if (Number.isSafeInteger(requested) && requested > 0) this.selectedChatId.set(requested);
    this.loadConversations();
    timer(10000, 10000).pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      if (!document.hidden) this.refresh();
    });
  }

  refresh(): void {
    this.loadConversations();
    const selected = this.selectedChatId();
    if (selected !== null) this.loadThread(selected);
  }

  loadConversations(): void {
    if (this.isLoading()) {
      return;
    }

    this.isLoading.set(true);
    this.loadError.set('');
    this.operational.listConversations({ limit: 100 }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (response) => {
        this.chats.set(response.items.map((item) => this.toChatContact(item)));
        const selected = this.selectedChat();
        if (!selected) {
          this.selectedChatId.set(null);
        } else if (!this.threads()[selected.id]) {
          this.loadThread(selected.id);
        }
        this.isLoading.set(false);
      },
      error: (error) => {
        this.loadError.set(this.operationalErrorMessage(error));
        this.isLoading.set(false);
      }
    });
  }

  select(chatId: number, trigger?: HTMLButtonElement): void {
    this.selectedChatId.set(chatId);
    if (trigger) {
      afterNextRender(() => {
        if (!trigger.getClientRects().length) {
          this.backButton()?.nativeElement.focus();
        }
      }, { injector: this.injector });
    }
    this.loadThread(chatId);
  }

  loadThread(chatId: number, older = false): void {
    const current = this.threads()[chatId] ?? { loading: false, error: false, hasOlder: false, messages: [] };
    if (current.loading) return;
    const beforeId = older ? current.messages[0]?.id : undefined;
    if (older && beforeId === undefined) return;
    this.threads.update((threads) => ({ ...threads, [chatId]: { ...current, loading: true, error: false } }));
    this.operational.listMessages(chatId, beforeId).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (response) => {
        const oldestReceived = response.items.at(-1)?.id;
        const missedPage = !older && oldestReceived !== undefined && current.messages.length > 0
          && oldestReceived > current.messages[current.messages.length - 1].id;
        const messages = new Map((missedPage ? [] : current.messages).map((message) => [message.id, message]));
        for (const item of response.items) messages.set(item.id, this.toMessage(item));
        this.threads.update((threads) => ({
          ...threads,
          [chatId]: {
            loading: false,
            error: false,
            hasOlder: response.total > (older ? response.items.length : messages.size),
            messages: [...messages.values()].sort((a, b) => a.id - b.id)
          }
        }));
      },
      error: () => {
        this.threads.update((threads) => ({ ...threads, [chatId]: { ...current, loading: false, error: true } }));
      }
    });
  }

  closeThread(): void {
    const chatId = this.selectedChatId();
    this.selectedChatId.set(null);
    afterNextRender(() => {
      const trigger = document.getElementById(`conversation-${chatId}`);
      (trigger ?? document.getElementById('conversation-search'))?.focus();
    }, { injector: this.injector });
  }

  clearFilters(): void {
    this.searchQuery.set('');
    this.filterStatus.set('all');
  }

  channelLabel(channel: ChatContact['channel']): string {
    return channel === 'web' ? 'Chat web' : channel === 'email' ? 'Correo' : 'WhatsApp';
  }

  statusLabel(status: ChatStatus): string {
    return { new: 'Nuevo', active: 'Activo', waiting: 'Esperando', closed: 'Cerrado' }[status];
  }

  leadLabel(status: LeadStatus): string {
    return { cold: 'Frío', warm: 'Tibio', hot: 'Caliente', converted: 'Convertido' }[status];
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
      name: conversation.lead_name || conversation.lead_phone || 'Contacto sin nombre',
      lastMessage: conversation.last_message || 'Sin mensajes registrados',
      timestamp: this.formatRelative(conversation.last_message_at || conversation.updated_at),
      status: this.mapConversationStatus(conversation),
      channel: this.mapChannel(conversation.channel),
      leadStatus: this.mapLeadStatus(conversation.temperature),
      requiresHuman: conversation.requires_human
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

  private operationalErrorMessage(error: unknown): string {
    if (!(error instanceof HttpErrorResponse)) {
      return 'No pudimos cargar las conversaciones.';
    }
    if (error.status === 401) {
      return 'Tu sesión expiró. Vuelve a iniciar sesión.';
    }
    if (error.status === 403) {
      return 'Tu espacio de trabajo tiene el acceso suspendido o pendiente.';
    }
    if (error.status === 404) {
      return 'Tu espacio de trabajo aún está pendiente de configuración.';
    }
    return 'No pudimos cargar las conversaciones.';
  }
}
