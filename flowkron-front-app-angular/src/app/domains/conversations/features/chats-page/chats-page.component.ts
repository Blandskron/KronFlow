import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, ElementRef, Injector, OnInit, afterNextRender, computed, inject, signal, viewChild } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute } from '@angular/router';
import { Subject, Subscription, debounceTime, timer } from 'rxjs';
import {
  LucideArrowLeft,
  LucideMail,
  LucideMessageSquare,
  LucidePhone,
  LucideRefreshCw,
  LucideSearch
} from '@lucide/angular';
import { Conversation, ConversationCursor, ConversationMessage, PendingReply } from '@domains/conversations/domain/conversation.model';
import { ConversationsApiService } from '@domains/conversations/data-access/conversations-api.service';
import { AuthService } from '@domains/auth/data-access/auth-api.service';

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
  unread: number;
}

interface Message {
  id: number;
  sender: 'user' | 'agent';
  text: string;
  timestamp: string;
  deliveryLabel?: string;
  deliveryFailure?: string;
}

interface Thread {
  loading: boolean;
  error: boolean;
  hasOlder: boolean;
  messages: Message[];
  pendingReplies: Partial<Record<number, PendingReply['status']>>;
}

const deliveryLabels = {
  unknown: 'Entrega desconocida', received: 'Entrega desconocida', sent: 'Enviado',
  failed: 'Falló el envío', delivered: 'Entregado', read: 'Leído'
};
const deliveryFailures = {
  provider_rejected: 'WhatsApp rechazó el envío.',
  account_restricted: 'WhatsApp restringió el envío desde esta cuenta.',
  connection_invalid: 'WhatsApp rechazó la sesión. Revisa la conexión.'
};

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
  private readonly auth = inject(AuthService);
  private readonly injector = inject(Injector);
  private readonly destroyRef = inject(DestroyRef);
  private readonly route = inject(ActivatedRoute);
  private readonly backButton = viewChild<ElementRef<HTMLButtonElement>>('backButton');
  private readonly filtersChanged = new Subject<void>();
  private readonly readThrough = new Map<number, number>();
  private listRequest?: Subscription;
  private paged = false;

  readonly searchQuery = signal('');
  readonly filterStatus = signal('all');
  readonly selectedChatId = signal<number | null>(null);
  private readonly selectedContact = signal<ChatContact | null>(null);
  readonly selectedChat = computed(() => this.chats().find((chat) => chat.id === this.selectedChatId()) ?? this.selectedContact());
  readonly nextCursor = signal<ConversationCursor | null>(null);
  readonly isLoading = signal(false);
  readonly loadError = signal('');
  readonly chats = signal<ChatContact[]>([]);
  readonly threads = signal<Partial<Record<number, Thread>>>({});
  readonly pendingReplyLabels = {
    queued: 'Respuesta en cola',
    sending: 'Enviando respuesta',
    unknown: 'Resultado del envío desconocido',
    not_sent: 'Respuesta pendiente de reprogramar'
  };

  readonly statuses = [
    { id: 'all', label: 'Todas' },
    { id: 'new', label: 'Nuevas' },
    { id: 'active', label: 'Activas' },
    { id: 'waiting', label: 'Necesitan atención' },
    { id: 'closed', label: 'Cerradas' }
  ];

  ngOnInit(): void {
    const params = this.route.snapshot.queryParamMap;
    const status = this.statuses.find((item) => item.id === params.get('status'));
    if (status) this.filterStatus.set(status.id);
    const requested = Number(params.get('conversation'));
    if (Number.isSafeInteger(requested) && requested > 0) this.openDeepLink(requested);
    this.filtersChanged.pipe(debounceTime(250), takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.loadConversations());
    this.loadConversations();
    timer(10000, 10000).pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      if (document.hidden) return;
      if (!this.paged && !this.isLoading()) this.loadConversations();
      const selected = this.selectedChatId();
      if (selected !== null) this.loadThread(selected);
    });
  }

  refresh(): void {
    this.loadConversations();
    const selected = this.selectedChatId();
    if (selected !== null) this.loadThread(selected);
  }

  loadConversations(append = false): void {
    const cursor = append ? this.nextCursor() : null;
    if (append && (!cursor || this.isLoading())) return;
    this.listRequest?.unsubscribe();
    this.isLoading.set(true);
    this.loadError.set('');
    this.listRequest = this.operational.listConversations({
      limit: 40,
      q: this.searchQuery().trim() || undefined,
      status: this.filterStatus() === 'all' ? undefined : this.filterStatus(),
      ...cursor
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (response) => {
        const contacts = new Map((append ? this.chats() : []).map((chat) => [chat.id, chat]));
        for (const item of response.items) contacts.set(item.id, this.toChatContact(item));
        const selected = this.selectedChatId();
        const updatedContact = selected === null ? undefined : contacts.get(selected);
        if (updatedContact) this.selectedContact.set(updatedContact);
        this.chats.set([...contacts.values()]);
        this.nextCursor.set(response.next_cursor ?? null);
        this.paged = append;
        this.isLoading.set(false);
      },
      error: (error) => {
        this.loadError.set(this.operationalErrorMessage(error));
        this.isLoading.set(false);
      }
    });
  }

  select(chatId: number, trigger?: HTMLButtonElement): void {
    this.selectedContact.set(this.chats().find((chat) => chat.id === chatId) ?? null);
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
    const current = this.threads()[chatId] ?? {
      loading: false, error: false, hasOlder: false, messages: [], pendingReplies: {}
    };
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
            messages: [...messages.values()].sort((a, b) => a.id - b.id),
            pendingReplies: older ? current.pendingReplies : Object.fromEntries(
              (response.pending_replies ?? []).map((reply) => [reply.inbound_message_id, reply.status])
            )
          }
        }));
        if (!older && this.selectedChatId() === chatId) {
          const newest = response.items[0]?.id;
          if (newest !== undefined) {
            afterNextRender(() => this.markVisibleThreadRead(chatId, newest), { injector: this.injector });
          }
        }
      },
      error: () => {
        this.threads.update((threads) => ({ ...threads, [chatId]: { ...current, loading: false, error: true } }));
      }
    });
  }

  closeThread(): void {
    const chatId = this.selectedChatId();
    this.selectedChatId.set(null);
    this.selectedContact.set(null);
    afterNextRender(() => {
      const trigger = document.getElementById(`conversation-${chatId}`);
      (trigger ?? document.getElementById('conversation-search'))?.focus();
    }, { injector: this.injector });
  }

  clearFilters(): void {
    this.searchQuery.set('');
    this.filterStatus.set('all');
    this.reloadFilters();
  }

  searchFor(query: string): void {
    this.searchQuery.set(query);
    this.reloadFilters();
  }

  filterBy(status: string): void {
    if (this.filterStatus() === status) return;
    this.filterStatus.set(status);
    this.reloadFilters();
  }

  private reloadFilters(): void {
    this.listRequest?.unsubscribe();
    this.chats.set([]);
    this.nextCursor.set(null);
    this.paged = false;
    this.isLoading.set(true);
    this.loadError.set('');
    this.filtersChanged.next();
  }

  private openDeepLink(chatId: number): void {
    this.selectedChatId.set(chatId);
    this.operational.getConversation(chatId).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (conversation) => {
        if (this.selectedChatId() !== chatId) return;
        this.selectedContact.set(this.toChatContact(conversation));
        this.loadThread(chatId);
      },
      error: () => {
        if (this.selectedChatId() === chatId) this.selectedChatId.set(null);
      }
    });
  }

  private markVisibleThreadRead(chatId: number, through: number): void {
    if (this.selectedChatId() !== chatId || document.hidden || !this.auth.hasPermission('crm.manage')
        || (this.readThrough.get(chatId) ?? 0) >= through) return;
    this.readThrough.set(chatId, through);
    this.operational.markRead(chatId, through).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: ({ no_leidos }) => {
        if (this.readThrough.get(chatId) !== through) return;
        this.chats.update((chats) => chats.map((chat) => chat.id === chatId ? { ...chat, unread: no_leidos } : chat));
        const selected = this.selectedContact();
        if (selected?.id === chatId) this.selectedContact.set({ ...selected, unread: no_leidos });
      },
      error: () => {
        if (this.readThrough.get(chatId) === through) this.readThrough.delete(chatId);
      }
    });
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
      requiresHuman: conversation.requires_human,
      unread: conversation.no_leidos ?? 0
    };
  }

  private toMessage(message: ConversationMessage): Message {
    const outbound = message.sender_type !== 'lead';
    return {
      id: message.id,
      sender: outbound ? 'agent' : 'user',
      text: message.body,
      timestamp: this.formatTime(message.sent_at),
      deliveryLabel: outbound ? deliveryLabels[message.delivery_status ?? 'unknown'] : undefined,
      deliveryFailure: outbound && message.delivery_failure_reason
        ? deliveryFailures[message.delivery_failure_reason] : undefined
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
