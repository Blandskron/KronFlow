import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { forkJoin } from 'rxjs';
import {
  LucideArrowDownUp,
  LucideClock,
  LucideGlobe,
  LucideInfo,
  LucideMail,
  LucidePhone,
  LucideSearch
} from '@lucide/angular';
import { Lead } from '@domains/leads/domain/lead.model';
import { Conversation } from '@domains/conversations/domain/conversation.model';
import { AuthService } from '@domains/auth/data-access/auth-api.service';
import { LeadsApiService } from '@domains/leads/data-access/leads-api.service';
import { ConversationsApiService } from '@domains/conversations/data-access/conversations-api.service';

interface Ticket {
  id: number;
  customerName: string;
  message: string;
  timestamp: string;
  channel: 'whatsapp' | 'email' | 'web';
  temperature: 'cold' | 'warm' | 'hot' | 'unqualified';
  origin: 'inbound' | 'outbound';
  progress: 'new' | 'active' | 'followup' | 'human';
  score: number;
  closed: boolean;
}

interface TicketColumn {
  title: string;
  tickets: Ticket[];
  accent: 'primary' | 'warning';
}

@Component({
  selector: 'flowkron-workflows-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    RouterLink,
    LucideArrowDownUp,
    LucideClock,
    LucideGlobe,
    LucideInfo,
    LucideMail,
    LucidePhone,
    LucideSearch
  ],
  templateUrl: './workflows-page.component.html',
  styleUrl: './workflows-page.component.css'
})
export class WorkflowsPageComponent implements OnInit {
  private readonly auth = inject(AuthService);
  private readonly operational = inject(LeadsApiService);
  private readonly conversationsService = inject(ConversationsApiService);

  readonly tenantName = computed(() => this.auth.currentTenant()?.name || 'Espacio de trabajo');
  readonly searchQuery = signal('');
  readonly statusFilter = signal<'open' | 'all' | 'closed'>('open');
  readonly originFilter = signal<'all' | 'inbound' | 'outbound'>('all');
  readonly temperatureFilter = signal<'all' | Ticket['temperature']>('all');
  readonly tickets = signal<Ticket[]>([]);
  readonly isLoading = signal(false);
  readonly loadError = signal('');
  readonly columns = computed<TicketColumn[]>(() => {
    const tickets = this.filteredTickets();
    return [
      { title: 'Nuevos', accent: 'primary', tickets: tickets.filter((ticket) => ticket.progress === 'new') },
      { title: 'En proceso', accent: 'primary', tickets: tickets.filter((ticket) => ticket.progress === 'active') },
      { title: 'Requieren seguimiento', accent: 'primary', tickets: tickets.filter((ticket) => ticket.progress === 'followup') },
      { title: 'Ayuda humana', accent: 'warning', tickets: tickets.filter((ticket) => ticket.progress === 'human') }
    ];
  });
  readonly filteredTickets = computed(() => {
    const query = this.searchQuery().toLowerCase().trim();
    const status = this.statusFilter();
    const origin = this.originFilter();
    const temperature = this.temperatureFilter();
    return this.tickets().filter((ticket) => {
      const matchesQuery = !query || ticket.customerName.toLowerCase().includes(query) || ticket.message.toLowerCase().includes(query);
      const matchesStatus =
        status === 'all' ||
        (status === 'closed' && ticket.closed) ||
        (status === 'open' && !ticket.closed);
      const matchesOrigin = origin === 'all' || ticket.origin === origin;
      const matchesTemperature = temperature === 'all' || ticket.temperature === temperature;
      return matchesQuery && matchesStatus && matchesOrigin && matchesTemperature;
    });
  });

  ngOnInit(): void {
    this.loadWorkflow();
  }

  loadWorkflow(): void {
    if (this.isLoading()) {
      return;
    }

    this.isLoading.set(true);
    this.loadError.set('');
    forkJoin({
      conversations: this.conversationsService.listConversations({ limit: 100 }),
      leads: this.operational.listLeads({ limit: 200 })
    }).subscribe({
      next: ({ conversations, leads }) => {
        const leadsById = new Map<number, Lead>(leads.items.map((lead) => [lead.id, lead]));
        this.tickets.set(conversations.items.map((conversation: Conversation) => this.toTicket(conversation, leadsById.get(conversation.lead_id))));
        this.isLoading.set(false);
      },
      error: (error: HttpErrorResponse) => {
        this.loadError.set(this.operationalErrorMessage(error));
        this.isLoading.set(false);
      }
    });
  }

  temperatureLabel(temperature: Ticket['temperature']): string {
    return { cold: 'Frío', warm: 'Tibio', hot: 'Caliente', unqualified: 'Sin calificar' }[temperature];
  }

  temperatureClass(temperature: Ticket['temperature']): string {
    if (temperature === 'hot') {
      return 'badge-danger';
    }

    if (temperature === 'warm') {
      return 'badge-warning';
    }

    return temperature === 'unqualified' ? 'badge-primary' : 'badge-info';
  }

  private toTicket(conversation: Conversation, lead?: Lead): Ticket {
    const temperature = this.mapTemperature(conversation.temperature || lead?.temperature || null);
    const isClosed = conversation.status === 'closed';
    return {
      id: conversation.id,
      customerName: conversation.lead_name || lead?.full_name || conversation.lead_phone || lead?.phone || 'Lead sin nombre',
      message: conversation.last_message || (isClosed ? 'Conversacion cerrada sin ultimo mensaje.' : 'Esperando primer mensaje registrado.'),
      timestamp: this.formatRelative(conversation.last_message_at || conversation.updated_at),
      channel: this.mapChannel(conversation.channel),
      temperature,
      origin: lead?.direction === 'outbound' ? 'outbound' : 'inbound',
      progress: this.mapProgress(conversation, temperature),
      score: lead?.score ?? this.scoreFromTemperature(temperature),
      closed: isClosed
    };
  }

  private mapProgress(conversation: Conversation, temperature: Ticket['temperature']): Ticket['progress'] {
    if (conversation.requires_human) {
      return 'human';
    }
    if (conversation.status === 'new') {
      return 'new';
    }
    if (temperature === 'hot' || conversation.status === 'waiting') {
      return 'followup';
    }
    return 'active';
  }

  private mapTemperature(value: string | null): Ticket['temperature'] {
    if (value === 'hot' || value === 'warm' || value === 'cold') {
      return value;
    }
    return 'unqualified';
  }

  private mapChannel(channel: string): Ticket['channel'] {
    return channel === 'email' ? 'email' : channel === 'web' || channel === 'webchat' ? 'web' : 'whatsapp';
  }

  private scoreFromTemperature(temperature: Ticket['temperature']): number {
    return { hot: 90, warm: 60, cold: 25, unqualified: 0 }[temperature];
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
      return 'No pudimos cargar el workflow del servicio operacional.';
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
    return 'No pudimos cargar el workflow del servicio operacional.';
  }
}
