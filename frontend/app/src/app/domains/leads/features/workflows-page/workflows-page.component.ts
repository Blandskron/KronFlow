import { DatePipe, JsonPipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
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
import {
  WorkflowDefinitionItem,
  WorkflowGraph,
  WorkflowRunItem,
  WorkflowSimulationResult,
  WorkflowTemplateItem,
  WorkflowValidationResult
} from '@domains/leads/domain/workflow-engine.model';
import { Conversation } from '@domains/conversations/domain/conversation.model';
import { AuthService } from '@domains/auth/data-access/auth-api.service';
import { LeadsApiService } from '@domains/leads/data-access/leads-api.service';
import { WorkflowsApiService } from '@domains/leads/data-access/workflows-api.service';
import { ConversationsApiService } from '@domains/conversations/data-access/conversations-api.service';
import {
  AlertComponent,
  BadgeComponent,
  BadgeTone,
  EmptyStateComponent,
  PageHeaderComponent,
  SkeletonComponent,
  TabItem,
  TabsComponent
} from '@shared/ui';

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

const TRIGGER_OPTIONS: readonly string[] = [
  'lead.created',
  'lead.captured',
  'lead.stage.changed',
  'lead.temperature.changed',
  'opportunity.created',
  'opportunity.stage.changed',
  'opportunity.won',
  'opportunity.lost',
  'conversation.handoff.requested',
  'message.inbound.received',
  'campaign.approved',
  'ai.proposal.executed'
];

@Component({
  selector: 'kronflow-workflows-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    DatePipe,
    JsonPipe,
    ReactiveFormsModule,
    RouterLink,
    LucideArrowDownUp,
    LucideClock,
    LucideGlobe,
    LucideInfo,
    LucideMail,
    LucidePhone,
    LucideSearch,
    PageHeaderComponent,
    TabsComponent,
    AlertComponent,
    BadgeComponent,
    EmptyStateComponent,
    SkeletonComponent
  ],
  templateUrl: './workflows-page.component.html',
  styleUrl: './workflows-page.component.css'
})
export class WorkflowsPageComponent implements OnInit {
  private readonly auth = inject(AuthService);
  private readonly operational = inject(LeadsApiService);
  private readonly workflowsApi = inject(WorkflowsApiService);
  private readonly conversationsService = inject(ConversationsApiService);
  private readonly fb = inject(FormBuilder);
  private readonly destroyRef = inject(DestroyRef);

  readonly tabs: readonly TabItem[] = [
    { id: 'studio', label: 'Automatizaciones' },
    { id: 'board', label: 'Tablero operativo' }
  ];
  readonly activeTab = signal<'studio' | 'board'>('studio');
  readonly triggerOptions = TRIGGER_OPTIONS;
  readonly canManage = computed(() => this.auth.hasPermission('crm.manage'));

  // Automation Studio state
  readonly templates = signal<WorkflowTemplateItem[]>([]);
  readonly workflows = signal<WorkflowDefinitionItem[]>([]);
  readonly runs = signal<WorkflowRunItem[]>([]);
  readonly selectedWorkflowId = signal<number | null>(null);
  readonly studioLoading = signal(false);
  readonly studioBusy = signal(false);
  readonly studioNotice = signal<{ tone: 'success' | 'danger' | 'info'; text: string } | null>(null);
  readonly validationResult = signal<WorkflowValidationResult | null>(null);
  readonly simulationResult = signal<WorkflowSimulationResult | null>(null);

  readonly selectedWorkflow = computed(
    () => this.workflows().find((item) => item.id === this.selectedWorkflowId()) ?? null
  );

  readonly statusTones: Record<string, BadgeTone> = {
    active: 'success',
    completed: 'success',
    draft: 'warning',
    waiting: 'warning',
    running: 'info',
    paused: 'neutral',
    archived: 'neutral',
    cancelled: 'neutral',
    failed: 'danger'
  };

  readonly studioForm = this.fb.nonNullable.group({
    name: ['', [Validators.required, Validators.maxLength(160)]],
    description: ['', [Validators.maxLength(500)]],
    triggerEventType: ['lead.created', [Validators.required]],
    graphJson: ['', [Validators.required]],
    publishNote: ['', [Validators.maxLength(240)]],
    samplePayloadJson: ['{\n  "temperature": "hot"\n}']
  });

  // Legacy operational board state
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
      const matchesQuery =
        !query || ticket.customerName.toLowerCase().includes(query) || ticket.message.toLowerCase().includes(query);
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
    this.loadStudio();
    this.loadWorkflow();
  }

  setTab(tab: string): void {
    if (tab === 'studio' || tab === 'board') {
      this.activeTab.set(tab);
    }
  }

  loadStudio(preferredId?: number | null): void {
    this.studioLoading.set(true);
    forkJoin({
      templates: this.workflowsApi.listTemplates(),
      workflows: this.workflowsApi.listWorkflows(),
      runs: this.workflowsApi.listRuns({ limit: 30 })
    })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: ({ templates, workflows, runs }) => {
          this.templates.set(templates);
          this.workflows.set(workflows);
          this.runs.set(runs);
          this.studioLoading.set(false);
          const targetId = preferredId ?? this.selectedWorkflowId();
          const match = (targetId ? workflows.find((w) => w.id === targetId) : null) ?? workflows[0] ?? null;
          if (match) {
            this.selectWorkflow(match);
          } else if (templates[0]) {
            this.prefillFromTemplate(templates[0]);
          }
        },
        error: () => {
          this.studioLoading.set(false);
          this.studioNotice.set({ tone: 'danger', text: 'No pudimos cargar las automatizaciones del tenant.' });
        }
      });
  }

  selectWorkflow(wf: WorkflowDefinitionItem): void {
    this.selectedWorkflowId.set(wf.id);
    this.validationResult.set(null);
    this.simulationResult.set(null);
    this.studioForm.patchValue({
      name: wf.name,
      description: wf.description,
      triggerEventType: wf.trigger_event_type,
      graphJson: JSON.stringify(wf.draft_graph, null, 2),
      publishNote: ''
    });
  }

  prefillFromTemplate(tpl: WorkflowTemplateItem): void {
    this.selectedWorkflowId.set(null);
    this.validationResult.set(null);
    this.simulationResult.set(null);
    this.studioForm.patchValue({
      name: tpl.name,
      description: tpl.description,
      triggerEventType: tpl.trigger_event_type,
      graphJson: JSON.stringify(tpl.graph, null, 2),
      publishNote: ''
    });
  }

  createFromTemplate(tpl: WorkflowTemplateItem): void {
    if (!this.canManage() || this.studioBusy()) return;
    this.studioBusy.set(true);
    this.workflowsApi
      .createWorkflow({
        name: tpl.name,
        description: tpl.description,
        trigger_event_type: tpl.trigger_event_type,
        graph: tpl.graph
      })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (created) => {
          this.studioBusy.set(false);
          this.studioNotice.set({ tone: 'success', text: `Borrador "${created.name}" creado desde plantilla.` });
          this.loadStudio(created.id);
        },
        error: (err: HttpErrorResponse) => this.handleStudioError(err, 'No pudimos crear desde la plantilla.')
      });
  }

  saveDraft(): void {
    if (!this.canManage() || this.studioBusy()) return;
    if (this.studioForm.invalid) {
      this.studioForm.markAllAsTouched();
      this.studioNotice.set({ tone: 'danger', text: 'Completa nombre, disparador y grafo JSON.' });
      return;
    }
    const raw = this.studioForm.getRawValue();
    let parsedGraph: WorkflowGraph;
    try {
      parsedGraph = JSON.parse(raw.graphJson) as WorkflowGraph;
    } catch {
      this.studioNotice.set({ tone: 'danger', text: 'El grafo JSON tiene un error de sintaxis.' });
      return;
    }

    const current = this.selectedWorkflow();
    this.studioBusy.set(true);
    if (!current) {
      this.workflowsApi
        .createWorkflow({
          name: raw.name.trim(),
          description: raw.description.trim(),
          trigger_event_type: raw.triggerEventType,
          graph: parsedGraph
        })
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe({
          next: (created) => {
            this.studioBusy.set(false);
            this.studioNotice.set({ tone: 'success', text: `Automatización "${created.name}" creada (v1).` });
            this.loadStudio(created.id);
          },
          error: (err: HttpErrorResponse) => this.handleStudioError(err, 'No pudimos crear la automatización.')
        });
      return;
    }

    this.workflowsApi
      .updateDraft(current.id, {
        name: raw.name.trim(),
        description: raw.description.trim(),
        trigger_event_type: raw.triggerEventType,
        graph: parsedGraph,
        expected_version: current.draft_version
      })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (updated) => {
          this.studioBusy.set(false);
          this.studioNotice.set({ tone: 'success', text: `Borrador guardado (v${updated.draft_version}).` });
          this.loadStudio(updated.id);
        },
        error: (err: HttpErrorResponse) => this.handleStudioError(err, 'No pudimos actualizar el borrador.')
      });
  }

  validateDraft(): void {
    const current = this.selectedWorkflow();
    if (!current || !this.canManage() || this.studioBusy()) return;
    this.studioBusy.set(true);
    this.workflowsApi
      .validateWorkflow(current.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          this.studioBusy.set(false);
          this.validationResult.set(res);
          this.studioNotice.set({
            tone: res.valid ? 'success' : 'danger',
            text: res.valid ? 'El grafo es válido y acíclico.' : 'El compilador detectó errores en el grafo.'
          });
        },
        error: (err: HttpErrorResponse) => this.handleStudioError(err, 'Error validando el grafo.')
      });
  }

  simulateDraft(): void {
    const current = this.selectedWorkflow();
    if (!current || !this.canManage() || this.studioBusy()) return;
    let samplePayload: Record<string, unknown> = {};
    try {
      const raw = this.studioForm.controls.samplePayloadJson.value.trim();
      samplePayload = raw ? (JSON.parse(raw) as Record<string, unknown>) : {};
    } catch {
      this.studioNotice.set({ tone: 'danger', text: 'El payload de simulación no es JSON válido.' });
      return;
    }
    this.studioBusy.set(true);
    this.workflowsApi
      .simulateWorkflow(current.id, samplePayload)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          this.studioBusy.set(false);
          this.simulationResult.set(res);
        },
        error: (err: HttpErrorResponse) => this.handleStudioError(err, 'No pudimos simular la automatización.')
      });
  }

  publishSelected(): void {
    const current = this.selectedWorkflow();
    if (!current || !this.canManage() || this.studioBusy()) return;
    this.studioBusy.set(true);
    const note = this.studioForm.controls.publishNote.value.trim();
    this.workflowsApi
      .publishWorkflow(current.id, current.draft_version, note || undefined)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (rev) => {
          this.studioBusy.set(false);
          this.studioNotice.set({
            tone: 'success',
            text: `Revisión r${rev.revision_number} publicada y activada para "${current.name}".`
          });
          this.loadStudio(current.id);
        },
        error: (err: HttpErrorResponse) => this.handleStudioError(err, 'No pudimos publicar el borrador.')
      });
  }

  processTick(): void {
    if (!this.canManage() || this.studioBusy()) return;
    this.studioBusy.set(true);
    this.workflowsApi
      .processTick()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (summary) => {
          this.studioBusy.set(false);
          this.studioNotice.set({
            tone: 'info',
            text: `Ciclo ejecutado: ${summary['runs_started'] ?? 0} iniciadas, ${summary['runs_resumed'] ?? 0} reanudadas.`
          });
          this.loadStudio(this.selectedWorkflowId());
        },
        error: (err: HttpErrorResponse) => this.handleStudioError(err, 'Error procesando eventos de automatización.')
      });
  }

  cancelRun(run: WorkflowRunItem): void {
    if (!this.canManage() || this.studioBusy()) return;
    this.studioBusy.set(true);
    this.workflowsApi
      .cancelRun(run.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.studioBusy.set(false);
          this.studioNotice.set({ tone: 'success', text: `Ejecución #${run.id} cancelada.` });
          this.loadStudio(this.selectedWorkflowId());
        },
        error: (err: HttpErrorResponse) => this.handleStudioError(err, 'No pudimos cancelar la ejecución.')
      });
  }

  private handleStudioError(err: HttpErrorResponse, fallback: string): void {
    this.studioBusy.set(false);
    if (err.status === 409) {
      this.studioNotice.set({ tone: 'danger', text: 'El borrador cambió en otra sesión. Recargamos el estado actual.' });
      this.loadStudio(this.selectedWorkflowId());
      return;
    }
    const detail = err.error?.detail;
    const msg =
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail?.errors)
          ? String(detail.errors.join(' · '))
          : fallback;
    this.studioNotice.set({ tone: 'danger', text: msg });
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
    })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: ({ conversations, leads }) => {
          const leadsById = new Map<number, Lead>(leads.items.map((lead) => [lead.id, lead]));
          this.tickets.set(
            conversations.items.map((conversation: Conversation) =>
              this.toTicket(conversation, leadsById.get(conversation.lead_id))
            )
          );
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
      customerName:
        conversation.lead_name || lead?.full_name || conversation.lead_phone || lead?.phone || 'Lead sin nombre',
      message:
        conversation.last_message ||
        (isClosed ? 'Conversacion cerrada sin ultimo mensaje.' : 'Esperando primer mensaje registrado.'),
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
