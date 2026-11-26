import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { AgentCoreService, AgentsApiService } from '@domains/agents/data-access';
import { AgentProfile, AgentRevision, DocumentRead } from '@domains/agents/domain';
import { AuthService } from '@domains/auth/data-access/auth-api.service';
import {
  AlertComponent,
  BadgeComponent,
  BadgeTone,
  EmptyStateComponent,
  PageHeaderComponent,
  SkeletonComponent
} from '@shared/ui';

interface ToolOption {
  id: string;
  label: string;
}

const TOOL_OPTIONS: readonly ToolOption[] = [
  { id: 'handoff_human', label: 'Derivar a agente humano (handoff_human)' },
  { id: 'crm.contact.rename', label: 'Proponer renombrar contacto (crm.contact.rename)' },
  { id: 'crm.lead.update_stage', label: 'Proponer cambio de etapa del lead (crm.lead.update_stage)' },
  { id: 'crm.opportunity.add_note', label: 'Proponer nota en oportunidad (crm.opportunity.add_note)' },
  { id: 'crm.conversation.request_handoff', label: 'Solicitar handoff de conversación (crm.conversation.request_handoff)' }
];

@Component({
  selector: 'kronflow-agents-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    DatePipe,
    ReactiveFormsModule,
    PageHeaderComponent,
    AlertComponent,
    BadgeComponent,
    EmptyStateComponent,
    SkeletonComponent
  ],
  templateUrl: './agents-page.component.html',
  styleUrl: './agents-page.component.css'
})
export class AgentsPageComponent implements OnInit {
  private readonly api = inject(AgentsApiService);
  private readonly contextApi = inject(AgentCoreService);
  private readonly auth = inject(AuthService);
  private readonly fb = inject(FormBuilder);
  private readonly destroyRef = inject(DestroyRef);

  readonly toolOptions = TOOL_OPTIONS;
  readonly agents = signal<AgentProfile[]>([]);
  readonly activeDocuments = signal<DocumentRead[]>([]);
  readonly revisions = signal<AgentRevision[]>([]);
  readonly selectedAgentId = signal<number | null>(null);
  readonly selectedTools = signal<string[]>(['handoff_human']);
  readonly selectedDocIds = signal<number[]>([]);
  readonly loading = signal(false);
  readonly revisionsLoading = signal(false);
  readonly saving = signal(false);
  readonly notice = signal<{ tone: 'success' | 'danger' | 'info'; text: string } | null>(null);

  readonly canEdit = computed(() => this.auth.hasPermission('agents.create'));
  readonly selectedAgent = computed(
    () => this.agents().find((agent) => agent.id === this.selectedAgentId()) ?? null
  );

  readonly statusTones: Record<string, BadgeTone> = {
    active: 'success',
    draft: 'warning',
    archived: 'neutral',
    published: 'success',
    superseded: 'neutral'
  };

  readonly form = this.fb.nonNullable.group({
    name: ['', [Validators.required, Validators.maxLength(160)]],
    role: ['Asistente comercial', [Validators.required, Validators.maxLength(160)]],
    tone: ['professional', [Validators.required, Validators.maxLength(120)]],
    language: ['es', [Validators.required, Validators.minLength(2), Validators.maxLength(16)]],
    instructions: ['', [Validators.maxLength(12000)]],
    isDefault: [false],
    publishNote: ['', [Validators.maxLength(240)]]
  });

  ngOnInit(): void {
    this.reloadAll();
  }

  reloadAll(preferredId?: number | null): void {
    this.loading.set(true);
    this.api
      .listAgents()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (list) => {
          this.agents.set(list);
          this.loading.set(false);
          const targetId = preferredId ?? this.selectedAgentId();
          const match = (targetId ? list.find((item) => item.id === targetId) : null) ?? list[0] ?? null;
          if (match) {
            this.selectAgent(match);
          } else {
            this.startNewDraft();
          }
        },
        error: () => {
          this.loading.set(false);
          this.notice.set({ tone: 'danger', text: 'No pudimos cargar el catálogo de agentes IA.' });
        }
      });

    this.contextApi
      .getBusinessContextStatus()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (status) => {
          this.activeDocuments.set(status.documents.filter((doc) => doc.status === 'active'));
        },
        error: () => {
          this.activeDocuments.set([]);
        }
      });
  }

  startNewDraft(): void {
    this.selectedAgentId.set(null);
    this.revisions.set([]);
    this.selectedTools.set(['handoff_human']);
    this.selectedDocIds.set(this.activeDocuments().map((doc) => doc.id));
    this.form.reset({
      name: '',
      role: 'Asistente comercial',
      tone: 'professional',
      language: 'es',
      instructions: '',
      isDefault: this.agents().length === 0,
      publishNote: ''
    });
  }

  selectAgent(agent: AgentProfile): void {
    this.selectedAgentId.set(agent.id);
    this.selectedTools.set([...(agent.allowed_tools ?? [])]);
    this.selectedDocIds.set([...(agent.allowed_document_ids ?? [])]);
    this.form.reset({
      name: agent.name,
      role: agent.role,
      tone: agent.tone || 'professional',
      language: agent.language || 'es',
      instructions: agent.instructions || '',
      isDefault: agent.is_default,
      publishNote: ''
    });
    this.loadRevisions(agent.id);
  }

  loadRevisions(agentId: number): void {
    this.revisionsLoading.set(true);
    this.api
      .listRevisions(agentId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (list) => {
          this.revisions.set(list);
          this.revisionsLoading.set(false);
        },
        error: () => {
          this.revisions.set([]);
          this.revisionsLoading.set(false);
        }
      });
  }

  toggleTool(toolId: string, event: Event): void {
    const checked = (event.target as HTMLInputElement).checked;
    this.selectedTools.update((current) =>
      checked ? Array.from(new Set([...current, toolId])) : current.filter((item) => item !== toolId)
    );
  }

  toggleDocument(docId: number, event: Event): void {
    const checked = (event.target as HTMLInputElement).checked;
    this.selectedDocIds.update((current) =>
      checked ? Array.from(new Set([...current, docId])) : current.filter((item) => item !== docId)
    );
  }

  saveDraft(): void {
    if (!this.canEdit() || this.saving()) return;
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      this.notice.set({ tone: 'danger', text: 'Revisa los campos requeridos antes de guardar.' });
      return;
    }

    const raw = this.form.getRawValue();
    const current = this.selectedAgent();
    this.saving.set(true);

    if (!current) {
      this.api
        .configureAgent({
          name: raw.name.trim(),
          role: raw.role.trim(),
          tone: raw.tone.trim(),
          language: raw.language.trim(),
          instructions: raw.instructions,
          allowed_tools: this.selectedTools(),
          allowed_document_ids: this.selectedDocIds(),
          is_default: raw.isDefault
        })
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe({
          next: (created) => {
            this.saving.set(false);
            this.notice.set({ tone: 'success', text: `Borrador "${created.name}" creado (v${created.version}).` });
            this.reloadAll(created.id);
          },
          error: (err: HttpErrorResponse) => this.handleApiError(err, 'No pudimos crear el agente.')
        });
      return;
    }

    this.api
      .updateAgent(current.id, {
        name: raw.name.trim(),
        role: raw.role.trim(),
        tone: raw.tone.trim(),
        language: raw.language.trim(),
        instructions: raw.instructions,
        allowed_tools: this.selectedTools(),
        allowed_document_ids: this.selectedDocIds(),
        is_default: raw.isDefault,
        expected_version: current.version
      })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (updated) => {
          this.saving.set(false);
          this.notice.set({ tone: 'success', text: `Borrador "${updated.name}" guardado (v${updated.version}).` });
          this.reloadAll(updated.id);
        },
        error: (err: HttpErrorResponse) => this.handleApiError(err, 'No pudimos guardar el borrador.')
      });
  }

  publishSelected(): void {
    const current = this.selectedAgent();
    if (!current || !this.canEdit() || this.saving()) return;
    this.saving.set(true);
    const note = this.form.controls.publishNote.value.trim();

    this.api
      .publishAgent(current.id, current.version, note || undefined)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (rev) => {
          this.saving.set(false);
          this.form.controls.publishNote.setValue('');
          this.notice.set({
            tone: 'success',
            text: `Revisión r${rev.revision_number} publicada para "${rev.name}".`
          });
          this.reloadAll(current.id);
        },
        error: (err: HttpErrorResponse) => this.handleApiError(err, 'No pudimos publicar la revisión.')
      });
  }

  rollbackTo(revision: AgentRevision): void {
    const current = this.selectedAgent();
    if (!current || !this.canEdit() || this.saving()) return;
    this.saving.set(true);

    this.api
      .rollbackAgent(current.id, current.version, revision.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (updated) => {
          this.saving.set(false);
          this.notice.set({
            tone: 'success',
            text: `Agente "${updated.name}" restaurado desde la revisión r${revision.revision_number}.`
          });
          this.reloadAll(updated.id);
        },
        error: (err: HttpErrorResponse) => this.handleApiError(err, 'No pudimos restaurar la revisión.')
      });
  }

  private handleApiError(err: HttpErrorResponse, fallback: string): void {
    this.saving.set(false);
    const detail = typeof err.error?.detail === 'string' ? err.error.detail : null;
    if (err.status === 409) {
      this.notice.set({
        tone: 'danger',
        text: 'El borrador cambió en otra sesión. Recargamos la versión actual antes de continuar.'
      });
      this.reloadAll(this.selectedAgentId());
      return;
    }
    this.notice.set({ tone: 'danger', text: detail || fallback });
  }
}
