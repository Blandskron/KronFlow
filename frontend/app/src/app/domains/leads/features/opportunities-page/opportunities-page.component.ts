import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { AuthService } from '@domains/auth/data-access/auth-api.service';
import {
  OpportunitiesApiService,
  OpportunityItem,
  PipelineStage
} from '@domains/leads/data-access/opportunities-api.service';
import {
  AlertComponent,
  BadgeComponent,
  BadgeTone,
  EmptyStateComponent,
  PageHeaderComponent,
  SkeletonComponent
} from '@shared/ui';

@Component({
  selector: 'kronflow-opportunities-page',
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
  templateUrl: './opportunities-page.component.html',
  styleUrl: './opportunities-page.component.css'
})
export class OpportunitiesPageComponent implements OnInit {
  private readonly api = inject(OpportunitiesApiService);
  private readonly auth = inject(AuthService);
  private readonly fb = inject(FormBuilder);
  private readonly destroyRef = inject(DestroyRef);

  readonly stages = signal<PipelineStage[]>([]);
  readonly items = signal<OpportunityItem[]>([]);
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly outcomeFilter = signal('');
  readonly notice = signal<{ error: boolean; text: string } | null>(null);
  readonly canManage = computed(() => this.auth.hasPermission('crm.manage'));

  readonly createForm = this.fb.nonNullable.group({
    title: ['', [Validators.required, Validators.maxLength(160)]],
    contactId: ['', [Validators.required, Validators.min(1)]],
    amount: [''],
    currency: ['USD', [Validators.maxLength(3)]]
  });

  readonly outcomeFilters = [
    { id: '', label: 'Todas' },
    { id: 'open', label: 'Abiertas' },
    { id: 'won', label: 'Ganadas' },
    { id: 'lost', label: 'Perdidas' }
  ];
  readonly outcomeLabels: Record<OpportunityItem['outcome'], string> = {
    open: 'Abierta',
    won: 'Ganada',
    lost: 'Perdida'
  };
  readonly outcomeTones: Record<OpportunityItem['outcome'], BadgeTone> = {
    open: 'info',
    won: 'success',
    lost: 'danger'
  };

  ngOnInit(): void {
    this.api.listStages().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (stages) => this.stages.set(stages),
      error: () => undefined
    });
    this.reload();
  }

  setOutcomeFilter(outcome: string): void {
    this.outcomeFilter.set(outcome);
    this.reload();
  }

  reload(): void {
    this.loading.set(true);
    const outcome = this.outcomeFilter() || undefined;
    this.api.list({ outcome, limit: 50 }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (page) => {
        this.items.set(page.items);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.notice.set({ error: true, text: 'No pudimos cargar las oportunidades.' });
      }
    });
  }

  createOpportunity(): void {
    if (this.createForm.invalid || this.saving()) return;
    const raw = this.createForm.getRawValue();
    const contactId = Number(raw.contactId);
    if (!raw.title.trim() || !Number.isSafeInteger(contactId) || contactId < 1) return;

    this.saving.set(true);
    this.notice.set(null);
    const amountVal = raw.amount.trim() ? Number(raw.amount) : undefined;
    this.api
      .create({
        title: raw.title.trim(),
        contact_id: contactId,
        amount: Number.isFinite(amountVal) ? amountVal : undefined,
        currency: raw.currency.trim().toUpperCase() || 'USD'
      })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.createForm.reset({ title: '', contactId: '', amount: '', currency: 'USD' });
          this.saving.set(false);
          this.notice.set({ error: false, text: 'Oportunidad creada.' });
          this.reload();
        },
        error: () => {
          this.saving.set(false);
          this.notice.set({ error: true, text: 'No pudimos crear la oportunidad. Verifica el ID de contacto.' });
        }
      });
  }

  moveStage(opp: OpportunityItem, stageId: number): void {
    if (stageId === opp.stage_id || this.saving()) return;
    this.saving.set(true);
    this.api
      .update(opp.id, { expected_version: opp.version, stage_id: stageId })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.saving.set(false);
          this.notice.set({ error: false, text: `Oportunidad #${opp.id} movida de etapa.` });
          this.reload();
        },
        error: (err: HttpErrorResponse) => {
          this.saving.set(false);
          this.notice.set({
            error: true,
            text:
              err.status === 409
                ? 'La oportunidad cambió en otra sesión. Recargando…'
                : 'No pudimos actualizar la etapa.'
          });
          if (err.status === 409) this.reload();
        }
      });
  }

  closeWon(opp: OpportunityItem): void {
    this.closeOpportunity(opp, 'won', 'Cerrada desde CRM', 'ganada');
  }

  closeLost(opp: OpportunityItem): void {
    this.closeOpportunity(opp, 'lost', 'Descartada desde CRM', 'perdida');
  }

  private closeOpportunity(
    opp: OpportunityItem,
    outcome: 'won' | 'lost',
    closeReason: string,
    label: string
  ): void {
    if (this.saving()) return;
    this.saving.set(true);
    this.api
      .update(opp.id, { expected_version: opp.version, outcome, close_reason: closeReason })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.saving.set(false);
          this.notice.set({ error: false, text: `Oportunidad #${opp.id} cerrada como ${label}.` });
          this.reload();
        },
        error: () => {
          this.saving.set(false);
          this.notice.set({ error: true, text: 'No pudimos cerrar la oportunidad.' });
        }
      });
  }
}
